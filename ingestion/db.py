"""
Supabase I/O for the ingestion pipeline.

All database reads and writes go through here. Sources and the pipeline
never construct a Supabase client directly.
"""

import json
import logging
import re
import uuid
from pathlib import Path

import geopandas as gpd
from shapely.geometry import shape

logger = logging.getLogger(__name__)

GEOJSON_PATH = Path(__file__).parent.parent / "data/geojson/miami_neighborhoods.geojson"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def get_client():
    import os
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]  # service role key — bypasses RLS for writes
    return create_client(url, key)


def seed_neighborhoods() -> int:
    """
    Upsert all 106 Miami neighborhoods from GeoJSON into the neighborhoods table.
    Idempotent — conflicts on slug. Safe to call on every pipeline run.
    """
    gdf = gpd.read_file(GEOJSON_PATH).to_crs("EPSG:4326")
    client = get_client()

    seen: set[str] = set()
    rows = []
    for _, row in gdf.iterrows():
        poly = row.geometry
        centroid = poly.centroid
        slug = _slug(row["name"])
        if slug in seen:
            logger.warning("Duplicate slug %r (name=%r) — skipping", slug, row["name"])
            continue
        seen.add(slug)
        rows.append({
            "name": row["name"],
            "slug": slug,
            "boundary": poly.wkt,
            "centroid": f"POINT({centroid.x} {centroid.y})",
        })

    client.table("neighborhoods").upsert(rows, on_conflict="slug").execute()
    logger.info("Seeded %d neighborhoods (%d duplicates dropped)", len(rows), len(gdf) - len(rows))
    return len(rows)


def write_scores(
    composite: dict[str, float],
    per_source: dict[str, dict[str, float]],
) -> str:
    """
    Insert one noise_scores row per neighborhood for a single pipeline run.

    Args:
        composite:  neighborhood → composite score (0–1)
        per_source: source_id → {neighborhood → normalized_score}

    Returns:
        run_id UUID string that groups all rows from this run
    """
    client = get_client()

    # Resolve neighborhood name → UUID (one round-trip)
    result = client.table("neighborhoods").select("id,name").execute()
    name_to_id = {r["name"]: r["id"] for r in result.data}

    run_id = str(uuid.uuid4())
    rows = []
    for name, score in composite.items():
        nbhd_id = name_to_id.get(name)
        if not nbhd_id:
            logger.warning("No DB record for neighborhood %r — skipping score write", name)
            continue
        rows.append({
            "neighborhood_id": nbhd_id,
            "run_id": run_id,
            "composite_score": round(score, 6),
            "source_scores": {
                s_id: round(scores.get(name, 0.0), 6)
                for s_id, scores in per_source.items()
            },
        })

    client.table("noise_scores").insert(rows).execute()
    logger.info("Wrote %d noise_scores rows (run_id=%s)", len(rows), run_id)
    return run_id


def write_corpus(documents: list) -> int:
    """
    Insert CorpusDocument instances into the reviews table.

    Resolves neighborhood names → UUIDs in a single round-trip.
    Skips documents whose neighborhood has no DB record (shouldn't happen
    after seed_neighborhoods, but safer to warn than to crash).

    Returns number of rows written.
    """
    from ingestion.sources.base import CorpusDocument

    if not documents:
        return 0

    client = get_client()
    result = client.table("neighborhoods").select("id,name").execute()
    name_to_id = {r["name"]: r["id"] for r in result.data}

    existing = client.table("reviews").select("neighborhood_id,content").execute()
    existing_pairs = {(r["neighborhood_id"], r["content"]) for r in existing.data}

    rows = []
    skipped_dup = 0
    for doc in documents:
        if not isinstance(doc, CorpusDocument):
            continue
        nbhd_id = name_to_id.get(doc.neighborhood)
        if not nbhd_id:
            logger.warning(
                "write_corpus: no DB record for neighborhood %r — skipping", doc.neighborhood
            )
            continue
        if (nbhd_id, doc.content) in existing_pairs:
            skipped_dup += 1
            continue
        rows.append({
            "neighborhood_id": nbhd_id,
            "source": doc.source_id,
            "content": doc.content,
            "author": doc.author or None,
            "external_url": doc.external_url or None,
            "metadata": doc.metadata,
        })

    if rows:
        client.table("reviews").insert(rows).execute()
    logger.info(
        "write_corpus: wrote %d review rows (%d skipped — no neighborhood, %d skipped — duplicates)",
        len(rows), len(documents) - len(rows) - skipped_dup, skipped_dup,
    )
    return len(rows)


def write_profile(neighborhood_name: str, profile_text: str, model: str = "gpt-4o-mini") -> None:
    """Insert a pre-generated profile row. latest_profiles view always returns the most recent."""
    client = get_client()
    result = client.table("neighborhoods").select("id").eq("name", neighborhood_name).execute()
    if not result.data:
        logger.warning("write_profile: no neighborhood record for %r — skipping", neighborhood_name)
        return
    client.table("profiles").insert({
        "neighborhood_id": result.data[0]["id"],
        "profile_text": profile_text,
        "model": model,
    }).execute()


def load_profile(neighborhood_name: str) -> str | None:
    """Return the latest pre-generated profile text for a neighborhood, or None."""
    client = get_client()
    result = (
        client.table("latest_profiles")
        .select("profile_text")
        .eq("neighborhood_name", neighborhood_name)
        .execute()
    )
    return result.data[0]["profile_text"] if result.data else None


def load_neighborhood_centroids() -> dict[str, tuple[float, float]]:
    """
    Read neighborhood centroids from GeoJSON (no DB round-trip).
    Returns name → (lat, lon).
    Used by sources that need centroids without a DB dependency.
    """
    with open(GEOJSON_PATH) as f:
        gj = json.load(f)
    result = {}
    for feature in gj["features"]:
        poly = shape(feature["geometry"])
        c = poly.centroid
        result[feature["properties"]["name"]] = (c.y, c.x)
    return result


def load_all_profiles() -> list[dict]:
    """Return all pre-generated profiles as [{neighborhood_name, profile_text}]."""
    client = get_client()
    result = client.table("latest_profiles").select("neighborhood_name,profile_text").execute()
    return result.data


def load_neighborhood_reviews(neighborhood_name: str) -> list[str]:
    """Return all review content texts for a neighborhood."""
    client = get_client()
    nbhd = client.table("neighborhoods").select("id").eq("name", neighborhood_name).execute()
    if not nbhd.data:
        return []
    nbhd_id = nbhd.data[0]["id"]
    result = client.table("reviews").select("content").eq("neighborhood_id", nbhd_id).execute()
    return [r["content"] for r in result.data]


def load_latest_scores() -> dict[str, float]:
    """Return {neighborhood_name: composite_score} from the latest_noise_scores view."""
    client = get_client()
    result = client.table("latest_noise_scores").select("neighborhood_name,composite_score").execute()
    return {r["neighborhood_name"]: r["composite_score"] for r in result.data}


def load_neighborhood_geodataframe() -> gpd.GeoDataFrame:
    """Load GeoJSON as a WGS84 GeoDataFrame. Used by spatial-join sources."""
    return gpd.read_file(GEOJSON_PATH).to_crs("EPSG:4326")
