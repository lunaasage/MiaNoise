import logging
import os
import time

import requests
from shapely.geometry import Point

from ingestion.db import load_neighborhood_centroids, load_neighborhood_geodataframe
from .base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)

PLACES_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
VENUE_TYPES = ["bar", "night_club", "restaurant"]
MAX_RADIUS_M = 1500  # upper bound for large neighborhoods like Allapattah


class VenueDensity(NoiseSource):
    """Google Places API — nightlife venue density per neighborhood."""

    source_id = "venue_density"
    weight = 0.5
    required_env_vars = ["GOOGLE_PLACES_API_KEY"]

    def fetch(self) -> list[NeighborhoodScore]:
        api_key = os.environ["GOOGLE_PLACES_API_KEY"]
        centroids = load_neighborhood_centroids()         # name → (lat, lon)
        radii = self._compute_radii()                     # name → radius_m

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
        Per-neighborhood search radius in meters = polygon circumradius, capped at
        MAX_RADIUS_M. Projected to UTM Zone 17N (EPSG:32617) for metric accuracy.
        Miami neighborhoods range from ~300m (Brickell Key) to ~1.5km (Allapattah).
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
        Count Places of a given type within radius_m of (lat, lon).
        Paginates up to 3 pages (60 results max per the Places API).
        """
        count = 0
        params = {
            "location": f"{lat},{lon}",
            "radius": radius_m,
            "type": place_type,
            "key": api_key,
        }
        for page in range(3):
            try:
                resp = requests.get(PLACES_URL, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "Places API error (type=%s page=%d): %s", place_type, page, exc
                )
                break

            count += len(data.get("results", []))
            token = data.get("next_page_token")
            if not token:
                break
            # Google requires ~2s before next_page_token is valid
            time.sleep(2)
            params = {"pagetoken": token, "key": api_key}

        return count
