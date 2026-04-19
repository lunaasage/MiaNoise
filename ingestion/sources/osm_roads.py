import logging
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import LineString

from ingestion.db import load_neighborhood_geodataframe
from .base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# overpass-api.de returns 406 without a User-Agent header
OVERPASS_HEADERS = {"User-Agent": "MiaNoise/1.0 (noise intelligence research)"}

# Road geometry is stable — cache locally to avoid depending on Overpass being
# available on every pipeline run. TTL of 7 days is appropriate for road networks.
CACHE_PATH = Path("data/cache/osm_roads_miami.gpkg")
CACHE_TTL_DAYS = 7

# Noise weight per road type. Motorways generate ~3× the noise energy of a
# primary road at equivalent traffic; weights reflect approximate dB contribution.
ROAD_WEIGHTS: dict[str, float] = {
    "motorway":      3.0,
    "motorway_link": 2.0,
    "trunk":         2.0,
    "trunk_link":    1.5,
    "primary":       1.0,
    "primary_link":  0.75,
}


class OSMRoadNoise(NoiseSource):
    """
    OpenStreetMap Overpass API — weighted road-km per neighborhood as a traffic
    noise proxy. Replaces TomTom/FDOT for the PoC.

    Score = sum(clipped_length_m × road_weight) per neighborhood, max-normalized.
    Road geometries are clipped to each neighborhood polygon before measuring length
    so a motorway that passes through two neighborhoods only counts for each
    proportionally.

    Road geometry is cached locally (data/cache/osm_roads_miami.gpkg, 7-day TTL)
    so the pipeline is not blocked by Overpass availability on every run.
    """

    source_id = "osm_roads"
    source_role = "scoring"
    weight = 0.4
    required_env_vars = []

    def fetch(self) -> list[NeighborhoodScore]:
        neighborhoods = load_neighborhood_geodataframe()[["name", "geometry"]]
        bbox = self._bbox(neighborhoods)

        roads_gdf = self._fetch_roads(bbox)
        if roads_gdf.empty:
            logger.warning("osm_roads: no road geometries returned")
            return self._zero_scores(neighborhoods)

        # Project both layers to UTM 17N for metric length calculation
        nbhd_utm  = neighborhoods.to_crs("EPSG:32617")
        roads_utm = roads_gdf.to_crs("EPSG:32617")

        # Clip roads to neighborhood boundaries, then measure weighted length.
        # df1=roads so keep_geom_type=True retains LineString results (correct);
        # df1=neighborhoods (polygons) would silently drop all LineString clippings.
        try:
            clipped = gpd.overlay(roads_utm, nbhd_utm, how="intersection")
        except Exception as exc:
            logger.warning("osm_roads: overlay failed: %s", exc)
            return self._zero_scores(neighborhoods)

        clipped["length_m"] = clipped.geometry.length
        clipped["weighted"] = clipped["length_m"] * clipped["road_weight"]

        raw = (
            clipped.groupby("name")["weighted"]
            .sum()
            .reindex(neighborhoods["name"], fill_value=0.0)
        )

        max_val = raw.max()
        if max_val == 0:
            return self._zero_scores(neighborhoods)

        logger.info(
            "osm_roads: weighted road signal — max=%.0fm, non-zero=%d neighborhoods",
            max_val, int((raw > 0).sum()),
        )
        return [
            NeighborhoodScore(
                neighborhood=name,
                normalized_score=round(val / max_val, 6),
                raw_value=round(val, 1),
                source_id=self.source_id,
                metadata={"weighted_road_m": round(val, 1)},
            )
            for name, val in raw.items()
        ]

    def _fetch_roads(self, bbox: str) -> gpd.GeoDataFrame:
        """
        Return road GeoDataFrame, using local cache when available and fresh.

        Cache strategy:
          1. Fresh cache (< CACHE_TTL_DAYS old) → serve from cache, skip Overpass
          2. No cache or stale → try Overpass; on success, write cache
          3. Overpass fails but stale cache exists → serve stale cache with warning
          4. Overpass fails and no cache → return empty GeoDataFrame
        """
        cache_age_days = self._cache_age_days()

        if cache_age_days is not None and cache_age_days < CACHE_TTL_DAYS:
            logger.info("osm_roads: loading from cache (age=%.1fd)", cache_age_days)
            return gpd.read_file(CACHE_PATH)

        gdf = self._fetch_from_overpass(bbox)

        if not gdf.empty:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            gdf.to_file(CACHE_PATH, driver="GPKG")
            logger.info("osm_roads: cached %d road segments to %s", len(gdf), CACHE_PATH)
            return gdf

        # Overpass failed — fall back to stale cache rather than returning zeros
        if cache_age_days is not None:
            logger.warning(
                "osm_roads: Overpass unavailable, using stale cache (age=%.1fd)", cache_age_days
            )
            return gpd.read_file(CACHE_PATH)

        return gpd.GeoDataFrame()

    def _fetch_from_overpass(self, bbox: str) -> gpd.GeoDataFrame:
        """Query Overpass for major road geometries. Returns empty GeoDataFrame on failure."""
        highway_filter = "|".join(ROAD_WEIGHTS.keys())
        query = f"""
[out:json][timeout:150];
(
  way["highway"~"^({highway_filter})$"]({bbox});
);
out geom;
"""
        elements = None
        for url in OVERPASS_ENDPOINTS:
            try:
                resp = requests.post(
                    url, data={"data": query}, headers=OVERPASS_HEADERS, timeout=180
                )
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
                logger.info("osm_roads: %d road elements from %s", len(elements), url)
                break
            except Exception as exc:
                logger.warning("osm_roads: %s failed: %s — trying next", url, exc)

        if elements is None:
            logger.warning("osm_roads: all Overpass endpoints failed")
            return gpd.GeoDataFrame()

        rows = []
        for el in elements:
            if el["type"] != "way" or "geometry" not in el:
                continue
            coords = [(pt["lon"], pt["lat"]) for pt in el["geometry"]]
            if len(coords) < 2:
                continue
            highway_type = el.get("tags", {}).get("highway", "")
            rows.append({
                "geometry":   LineString(coords),
                "highway":    highway_type,
                "road_weight": ROAD_WEIGHTS.get(highway_type, 1.0),
            })

        if not rows:
            return gpd.GeoDataFrame()

        return gpd.GeoDataFrame(rows, crs="EPSG:4326")

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
                source_id="osm_roads",
                metadata={"weighted_road_m": 0.0},
            )
            for _, row in neighborhoods.iterrows()
        ]
