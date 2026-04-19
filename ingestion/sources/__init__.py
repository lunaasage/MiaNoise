"""
Source registry. Add new NoiseSource subclasses here to make them pipeline-visible.
The pipeline imports ALL_SOURCES and calls is_available() on each — sources with
missing env vars are silently skipped, so the PoC and full version share the same
registry without any branching logic.
"""

from .base import NeighborhoodScore, NoiseSource
from .complaints_311 import Complaints311
from .construction import ConstructionPermits
from .opensky_flights import OpenSkyFlights
from .osm_roads import OSMRoadNoise
from .osm_venues import OSMVenueDensity
from .reddit_posts import RedditPosts
from .tomtom_traffic import TomTomTraffic
from .venue_density import VenueDensity
from .yelp_reviews import YelpReviews

# Ordered from highest to lowest default weight. The pipeline instantiates all of
# these; only those whose is_available() returns True will contribute to the score.
ALL_SOURCES: list[type[NoiseSource]] = [
    Complaints311,       # PoC — City of Miami 311 NOISEVIO, public API
    OSMVenueDensity,     # PoC — OSM bars/nightclubs/restaurants, no API key
    OSMRoadNoise,        # PoC — OSM weighted road-km, no API key
    VenueDensity,        # Sprint 2 enrichment — requires GOOGLE_PLACES_API_KEY, weight=0
    YelpReviews,         # Sprint 2 enrichment — requires YELP_API_KEY, weight=0
    RedditPosts,         # Sprint 2 enrichment — requires REDDIT_* keys, weight=0
    TomTomTraffic,       # Full version — requires TOMTOM_API_KEY
    OpenSkyFlights,      # Full version — requires OPENSKY_* credentials
    ConstructionPermits, # Full version — public API, is_available() returns False
]

__all__ = [
    "NoiseSource",
    "NeighborhoodScore",
    "ALL_SOURCES",
]
