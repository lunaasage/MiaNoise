"""
Google Places API (New) — review text corpus for the RAG pipeline.

For each neighborhood with OSM-mapped venues, searches nearby bars/nightclubs/
restaurants and collects up to 5 reviews per place. Reviews are returned as
CorpusDocument instances and persisted to the reviews table by the pipeline.

Venue types and radius logic match venue_density.py. Using the OSM venue cache
(if available) to identify which neighborhoods have venues avoids querying Places
for all 104 neighborhoods — most quiet residential ones have no relevant venues.
"""

import logging
import os
import time
from pathlib import Path

import requests

from ingestion.db import load_neighborhood_centroids, load_neighborhood_geodataframe
from .base import CorpusDocument, NoiseSource, NeighborhoodScore

logger = logging.getLogger(__name__)

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
VENUE_TYPES = ["bar", "night_club", "restaurant"]
MAX_RADIUS_M = 1500
OSM_CACHE_PATH = Path("data/cache/osm_venues_miami.gpkg")

REVIEW_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.userRatingCount,places.rating,places.reviews"
)


class GooglePlacesReviews(NoiseSource):
    """
    Corpus source: fetches review text from Google Places for bars/nightclubs/
    restaurants near each neighborhood. Returns list[CorpusDocument] for the
    RAG pipeline (not NeighborhoodScore — this source does not contribute to
    the composite noise score).
    """

    source_id = "google_places"
    source_role = "corpus"
    required_env_vars = ["GOOGLE_PLACES_API_KEY"]

    def fetch(self) -> list[CorpusDocument]:
        api_key = os.environ["GOOGLE_PLACES_API_KEY"]
        centroids = load_neighborhood_centroids()
        radii = self._compute_radii()
        active_neighborhoods = self._neighborhoods_with_venues(centroids)

        logger.info(
            "google_places: fetching reviews for %d neighborhoods with venues",
            len(active_neighborhoods),
        )

        documents: list[CorpusDocument] = []
        for name in active_neighborhoods:
            if name not in centroids:
                continue
            lat, lon = centroids[name]
            radius_m = radii.get(name, 800)
            nbhd_docs = self._fetch_neighborhood_reviews(name, lat, lon, radius_m, api_key)
            documents.extend(nbhd_docs)

        logger.info(
            "google_places: collected %d review documents across %d neighborhoods",
            len(documents),
            len({d.neighborhood for d in documents}),
        )
        return documents

    def _fetch_neighborhood_reviews(
        self, neighborhood: str, lat: float, lon: float, radius_m: int, api_key: str
    ) -> list[CorpusDocument]:
        docs: list[CorpusDocument] = []
        for venue_type in VENUE_TYPES:
            places = self._search_nearby(lat, lon, radius_m, venue_type, api_key)
            for place in places:
                venue_name = place.get("displayName", {}).get("text", "Unknown venue")
                rating = place.get("rating")
                review_count = place.get("userRatingCount", 0)
                for review in place.get("reviews", []):
                    text = review.get("text", {}).get("text", "").strip()
                    if not text:
                        continue
                    author = review.get("authorAttribution", {}).get("displayName", "")
                    # Prepend venue context so the embedding carries geographic signal
                    content = f"[{venue_name}, {neighborhood}] {text}"
                    docs.append(CorpusDocument(
                        neighborhood=neighborhood,
                        source_id=self.source_id,
                        content=content,
                        author=author,
                        metadata={
                            "venue_name": venue_name,
                            "venue_type": venue_type,
                            "venue_rating": rating,
                            "venue_review_count": review_count,
                        },
                    ))
            time.sleep(0.2)
        return docs

    @staticmethod
    def _search_nearby(
        lat: float, lon: float, radius_m: int, place_type: str, api_key: str
    ) -> list[dict]:
        body = {
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
            "X-Goog-FieldMask": REVIEW_FIELD_MASK,
        }
        try:
            resp = requests.post(PLACES_URL, json=body, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.json().get("places", [])
        except Exception as exc:
            logger.warning(
                "google_places: Places API error (type=%s): %s", place_type, exc
            )
            return []

    @staticmethod
    def _compute_radii() -> dict[str, int]:
        from shapely.geometry import Point
        gdf = load_neighborhood_geodataframe().to_crs("EPSG:32617")
        radii = {}
        for _, row in gdf.iterrows():
            poly = row.geometry
            centroid = poly.centroid
            r = max(centroid.distance(Point(c)) for c in poly.exterior.coords)
            radii[row["name"]] = min(int(r), MAX_RADIUS_M)
        return radii

    @staticmethod
    def _neighborhoods_with_venues(centroids: dict) -> list[str]:
        """
        Return neighborhoods that have at least one OSM-mapped venue.
        Falls back to all neighborhoods with centroids if cache is missing.
        """
        if OSM_CACHE_PATH.exists():
            import geopandas as gpd
            from ingestion.db import load_neighborhood_geodataframe as load_gdf
            venues_gdf = gpd.read_file(OSM_CACHE_PATH)
            nbhd_gdf = load_gdf()[["name", "geometry"]]
            joined = gpd.sjoin(
                venues_gdf[["geometry"]], nbhd_gdf, how="left", predicate="within"
            )
            counts = joined.groupby("name").size()
            return counts[counts > 0].index.tolist()
        logger.warning(
            "google_places: OSM venue cache not found at %s — querying all neighborhoods",
            OSM_CACHE_PATH,
        )
        return list(centroids.keys())
