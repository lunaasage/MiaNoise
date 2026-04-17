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
from .reddit_posts import RedditPosts
from .tomtom_traffic import TomTomTraffic
from .venue_density import VenueDensity
from .yelp_reviews import YelpReviews

# Ordered from highest to lowest default weight. The pipeline instantiates all of
# these; only those whose is_available() returns True will contribute to the score.
ALL_SOURCES: list[type[NoiseSource]] = [
    Complaints311,       # PoC — public API, always available
    VenueDensity,        # PoC — requires GOOGLE_PLACES_API_KEY
    YelpReviews,         # PoC — requires YELP_API_KEY (RAG corpus only, weight=0)
    RedditPosts,         # PoC — requires REDDIT_* keys (RAG corpus only, weight=0)
    TomTomTraffic,       # Full version — requires TOMTOM_API_KEY
    OpenSkyFlights,      # Full version — requires OPENSKY_* credentials
    ConstructionPermits, # Full version — public API, always available
]

__all__ = [
    "NoiseSource",
    "NeighborhoodScore",
    "ALL_SOURCES",
]
