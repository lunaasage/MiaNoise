import logging
import os
import time

import requests
from shapely.geometry import Point

from ingestion.db import load_neighborhood_centroids, load_neighborhood_geodataframe
from .base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)

# Google Places API (New) — Nearby Search
# The legacy Nearby Search API (maps.googleapis.com/maps/api/place/nearbysearch)
# requires a separate enablement; new projects default to the v1 API.
PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
VENUE_TYPES = ["bar", "night_club", "restaurant"]
MAX_RADIUS_M = 1500  # upper bound for large neighborhoods like Allapattah


class VenueDensity(NoiseSource):
    """Google Places API (New) — nightlife venue density per neighborhood."""

    source_id = "venue_density"
    source_role = "corpus"  # Sprint 2 enrichment — cross-validates OSMVenueDensity
    required_env_vars = ["GOOGLE_PLACES_API_KEY"]

    def fetch(self) -> list[NeighborhoodScore]:
        api_key = os.environ["GOOGLE_PLACES_API_KEY"]
        centroids = load_neighborhood_centroids()
        radii = self._compute_radii()

        counts: dict[str, dict] = {}
        for name, (lat, lon) in centroids.items():
            radius_m = radii.get(name, MAX_RADIUS_M)
            bar_count  = self._count_places(lat, lon, radius_m, "bar", api_key)
            club_count = self._count_places(lat, lon, radius_m, "night_club", api_key)
            rest_count = self._count_places(lat, lon, radius_m, "restaurant", api_key)
            total = bar_count + club_count + rest_count
            counts[name] = {
                "bar_count": bar_count,
                "club_count": club_count,
                "restaurant_count": rest_count,
                "total": total,
            }
            logger.debug("%s: %d venues (radius=%dm)", name, total, radius_m)

        totals = {name: c["total"] for name, c in counts.items()}
        max_total = max(totals.values(), default=1) or 1

        logger.info(
            "venue_density: max=%d venues, mean=%.1f, non-zero neighborhoods=%d",
            max_total,
            sum(totals.values()) / len(totals) if totals else 0,
            sum(1 for v in totals.values() if v > 0),
        )
        return [
            NeighborhoodScore(
                neighborhood=name,
                normalized_score=round(total / max_total, 6),
                raw_value=float(total),
                source_id=self.source_id,
                metadata=counts[name],
            )
            for name, total in totals.items()
        ]

    @staticmethod
    def _compute_radii() -> dict[str, int]:
        """
        Per-neighborhood search radius = polygon circumradius (UTM Zone 17N), capped at
        MAX_RADIUS_M. Avoids over-counting in small dense neighborhoods (Brickell Key
        ~300m) and under-counting in large ones (Allapattah ~1.5km).
        """
        gdf = load_neighborhood_geodataframe().to_crs("EPSG:32617")
        radii = {}
        for _, row in gdf.iterrows():
            poly = row.geometry
            centroid = poly.centroid
            circumradius = max(
                centroid.distance(Point(c)) for c in poly.exterior.coords
            )
            radii[row["name"]] = min(int(circumradius), MAX_RADIUS_M)
        return radii

    @staticmethod
    def _count_places(
        lat: float, lon: float, radius_m: int, place_type: str, api_key: str
    ) -> int:
        """
        Count Places of a given type within radius_m of (lat, lon) using the
        Places API (New). Paginates up to 3 pages (60 results max).
        """
        count = 0
        body: dict = {
            "includedTypes": [place_type],
            "maxResultCount": 20,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": float(radius_m),
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.id",  # nextPageToken is returned automatically
        }

        for page in range(3):
            try:
                resp = requests.post(
                    PLACES_URL, json=body, headers=headers, timeout=10
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "Places API error (type=%s page=%d): %s", place_type, page, exc
                )
                break

            places = data.get("places", [])
            count += len(places)

            token = data.get("nextPageToken")
            if not token:
                break
            body = {"pageToken": token}
            time.sleep(2)

        return count
