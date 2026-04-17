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


def load_neighborhood_geodataframe() -> gpd.GeoDataFrame:
    """Load GeoJSON as a WGS84 GeoDataFrame. Used by spatial-join sources."""
    return gpd.read_file(GEOJSON_PATH).to_crs("EPSG:4326")
