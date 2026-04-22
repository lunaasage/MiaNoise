import logging
import time
from pathlib import Path

import geopandas as gpd
import requests

from ingestion.db import load_neighborhood_geodataframe
from .base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# overpass-api.de returns 406 without a User-Agent header
OVERPASS_HEADERS = {"User-Agent": "MiaNoise/1.0 (noise intelligence research)"}

# Venue data cached locally to survive Overpass downtime. Shorter TTL than roads
# (1 day) since venues open and close; road network is stable for weeks.
# v2: cache path bumped to force re-fetch after adding amenity tag to schema.
CACHE_PATH = Path("data/cache/osm_venues_v2_miami.gpkg")
CACHE_TTL_DAYS = 1

# Venue types that drive nighttime noise
VENUE_AMENITIES = ["bar", "nightclub", "restaurant"]

# Noise weight per venue type. Nightclubs are 6× louder by impact than
# restaurants — loud music, late hours, outdoor crowds vs. ambient dining noise.
VENUE_WEIGHTS: dict[str, float] = {
    "nightclub":  3.0,
    "bar":        2.0,
    "restaurant": 0.5,
}


class OSMVenueDensity(NoiseSource):
    """
    OpenStreetMap Overpass API — bar/nightclub/restaurant density per neighborhood.

    Replaces Google Places venue_density for the PoC:
    - No API key required
    - No per-search quota (Google Places caps at 20 results per type per area)
    - Returns every mapped venue in Miami — typically 3–5× more complete
    - Bounding box is computed from the neighborhood GeoJSON at fetch time

    Venue points are cached locally (data/cache/osm_venues_v2_miami.gpkg, 1-day TTL)
    so the pipeline is not blocked by Overpass availability on every run.
    """

    source_id = "osm_venues"
    source_role = "scoring"
    weight = 0.6
    required_env_vars = []

    def fetch(self) -> list[NeighborhoodScore]:
        neighborhoods = load_neighborhood_geodataframe()[["name", "geometry"]]
        bbox = self._bbox(neighborhoods)

        venues_gdf = self._fetch_venues(bbox)
        if venues_gdf.empty:
            logger.warning("osm_venues: no venue data available")
            return self._zero_scores(neighborhoods)

        joined = gpd.sjoin(
            venues_gdf[["geometry", "amenity"]],
            neighborhoods,
            how="left",
            predicate="within",
        )
        joined["noise_weight"] = joined["amenity"].map(VENUE_WEIGHTS).fillna(0.5)

        raw_grouped = joined.groupby("name")["noise_weight"].sum()
        counts_grouped = joined.groupby("name").size()

        max_val = raw_grouped.max()
        if max_val == 0:
            return self._zero_scores(neighborhoods)

        logger.info(
            "osm_venues: %d venues across %d neighborhoods (max weighted=%.1f)",
            int(counts_grouped.sum()), len(counts_grouped), max_val,
        )
        seen: set[str] = set()
        results = []
        for name in neighborhoods["name"]:
            if name in seen:
                continue
            seen.add(name)
            raw_val = raw_grouped.get(name, 0.0)
            count_val = counts_grouped.get(name, 0)
            results.append(NeighborhoodScore(
                neighborhood=name,
                normalized_score=round(raw_val / max_val, 6),
                raw_value=round(raw_val, 2),
                source_id=self.source_id,
                metadata={"venue_count": int(count_val), "weighted_score": round(raw_val, 2)},
            ))
        return results

    def _fetch_venues(self, bbox: str) -> gpd.GeoDataFrame:
        """
        Return venue GeoDataFrame, using local cache when available and fresh.

        Cache strategy mirrors osm_roads: fresh cache → serve; stale/missing →
        try Overpass; on success write cache; on failure serve stale if available.
        """
        cache_age_days = self._cache_age_days()

        if cache_age_days is not None and cache_age_days < CACHE_TTL_DAYS:
            logger.info("osm_venues: loading from cache (age=%.2fd)", cache_age_days)
            return gpd.read_file(CACHE_PATH)

        elements = self._query_overpass(bbox)
        if elements:
            points = self._to_points(elements)
            if points:
                gdf = gpd.GeoDataFrame(
                    points,
                    geometry=gpd.points_from_xy(
                        [p["lon"] for p in points],
                        [p["lat"] for p in points],
                    ),
                    crs="EPSG:4326",
                )
                gdf = gdf[["geometry", "amenity"]]
                CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                gdf.to_file(CACHE_PATH, driver="GPKG")
                logger.info("osm_venues: cached %d venues to %s", len(gdf), CACHE_PATH)
                return gdf

        if cache_age_days is not None:
            logger.warning(
                "osm_venues: Overpass unavailable, using stale cache (age=%.2fd)", cache_age_days
            )
            return gpd.read_file(CACHE_PATH)

        return gpd.GeoDataFrame()

    def _query_overpass(self, bbox: str) -> list[dict]:
        amenity_regex = "|".join(VENUE_AMENITIES)
        query = f"""
[out:json][timeout:90];
(
  node["amenity"~"^({amenity_regex})$"]({bbox});
  way["amenity"~"^({amenity_regex})$"]({bbox});
);
out center;
"""
        for url in OVERPASS_ENDPOINTS:
            try:
                resp = requests.post(
                    url, data={"data": query}, headers=OVERPASS_HEADERS, timeout=120
                )
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
                logger.info("osm_venues: %d elements from %s", len(elements), url)
                return elements
            except Exception as exc:
                logger.warning("osm_venues: %s failed: %s — trying next", url, exc)
        logger.warning("osm_venues: all Overpass endpoints failed")
        return []

    @staticmethod
    def _to_points(elements: list[dict]) -> list[dict]:
        """Extract (lat, lon, amenity) from nodes and ways (ways carry center coords)."""
        points = []
        for el in elements:
            amenity = el.get("tags", {}).get("amenity", "restaurant")
            if el["type"] == "node":
                points.append({"lat": el["lat"], "lon": el["lon"], "amenity": amenity})
            elif el["type"] == "way" and "center" in el:
                points.append({"lat": el["center"]["lat"], "lon": el["center"]["lon"], "amenity": amenity})
        return points

    @staticmethod
    def _cache_age_days() -> float | None:
        """Return cache file age in days, or None if it doesn't exist."""
        if not CACHE_PATH.exists():
            return None
        return (time.time() - CACHE_PATH.stat().st_mtime) / 86400

    @staticmethod
    def _bbox(gdf: gpd.GeoDataFrame) -> str:
        bounds = gdf.total_bounds
        pad = 0.01
        return f"{bounds[1]-pad},{bounds[0]-pad},{bounds[3]+pad},{bounds[2]+pad}"

    @staticmethod
    def _zero_scores(neighborhoods: gpd.GeoDataFrame) -> list[NeighborhoodScore]:
        return [
            NeighborhoodScore(
                neighborhood=row["name"],
                normalized_score=0.0,
                raw_value=0.0,
                source_id="osm_venues",
                metadata={"venue_count": 0},
            )
            for _, row in neighborhoods.iterrows()
        ]
