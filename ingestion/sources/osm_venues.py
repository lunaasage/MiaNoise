import logging

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

from ingestion.db import load_neighborhood_geodataframe
from .base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Venue types that drive nighttime noise
VENUE_AMENITIES = ["bar", "nightclub", "restaurant"]


class OSMVenueDensity(NoiseSource):
    """
    OpenStreetMap Overpass API — bar/nightclub/restaurant density per neighborhood.

    Replaces Google Places venue_density for the PoC:
    - No API key required
    - No per-search quota (Google Places caps at 20 results per type per area)
    - Returns every mapped venue in Miami — typically 3–5× more complete
    - Bounding box is computed from the neighborhood GeoJSON at fetch time
    """

    source_id = "osm_venues"
    weight = 0.5
    required_env_vars = []

    def fetch(self) -> list[NeighborhoodScore]:
        neighborhoods = load_neighborhood_geodataframe()[["name", "geometry"]]
        bbox = self._bbox(neighborhoods)

        elements = self._query_overpass(bbox)
        if not elements:
            logger.warning("osm_venues: Overpass returned no elements")
            return self._zero_scores(neighborhoods)

        points = self._to_points(elements)
        if not points:
            logger.warning("osm_venues: no usable coordinates in Overpass response")
            return self._zero_scores(neighborhoods)

        venues_gdf = gpd.GeoDataFrame(
            points,
            geometry=gpd.points_from_xy(
                [p["lon"] for p in points],
                [p["lat"] for p in points],
            ),
            crs="EPSG:4326",
        )

        joined = gpd.sjoin(
            venues_gdf[["geometry"]],
            neighborhoods,
            how="left",
            predicate="within",
        )
        counts = (
            joined.groupby("name").size().reindex(neighborhoods["name"], fill_value=0)
        )

        max_count = counts.max()
        if max_count == 0:
            return self._zero_scores(neighborhoods)

        logger.info(
            "osm_venues: %d venues across %d neighborhoods (max=%d)",
            int(counts.sum()), int((counts > 0).sum()), int(max_count),
        )
        return [
            NeighborhoodScore(
                neighborhood=name,
                normalized_score=round(count / max_count, 6),
                raw_value=float(count),
                source_id=self.source_id,
                metadata={"venue_count": int(count)},
            )
            for name, count in counts.items()
        ]

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
                resp = requests.post(url, data={"data": query}, timeout=120)
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
        """Extract (lat, lon) from nodes and ways (ways carry center coords)."""
        points = []
        for el in elements:
            if el["type"] == "node":
                points.append({"lat": el["lat"], "lon": el["lon"]})
            elif el["type"] == "way" and "center" in el:
                points.append({"lat": el["center"]["lat"], "lon": el["center"]["lon"]})
        return points

    @staticmethod
    def _bbox(gdf: gpd.GeoDataFrame) -> str:
        """Compute Overpass bbox string (south,west,north,east) from GeoDataFrame."""
        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
        pad = 0.01  # ~1km padding so edge neighborhoods aren't clipped
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
