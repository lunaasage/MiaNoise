import logging

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString, MultiLineString, shape

from ingestion.db import load_neighborhood_geodataframe
from .base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

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
    """

    source_id = "osm_roads"
    weight = 0.2
    required_env_vars = []

    def fetch(self) -> list[NeighborhoodScore]:
        neighborhoods = load_neighborhood_geodataframe()[["name", "geometry"]]
        bbox = self._bbox(neighborhoods)

        roads_gdf = self._fetch_roads(bbox)
        if roads_gdf.empty:
            logger.warning("osm_roads: no road geometries returned")
            return self._zero_scores(neighborhoods)

        # Project both layers to UTM 17N for metric length calculation
        nbhd_utm   = neighborhoods.to_crs("EPSG:32617")
        roads_utm  = roads_gdf.to_crs("EPSG:32617")

        # Clip roads to neighborhood boundaries, then measure weighted length
        try:
            clipped = gpd.overlay(nbhd_utm, roads_utm, how="intersection")
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
        """Query Overpass for major road geometries and return as GeoDataFrame."""
        highway_filter = "|".join(ROAD_WEIGHTS.keys())
        query = f"""
[out:json][timeout:90];
(
  way["highway"~"^({highway_filter})$"]({bbox});
);
out geom;
"""
        elements = None
        for url in OVERPASS_ENDPOINTS:
            try:
                resp = requests.post(url, data={"data": query}, timeout=120)
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
                "geometry": LineString(coords),
                "highway":  highway_type,
                "road_weight": ROAD_WEIGHTS.get(highway_type, 1.0),
            })

        if not rows:
            return gpd.GeoDataFrame()

        return gpd.GeoDataFrame(rows, crs="EPSG:4326")

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
