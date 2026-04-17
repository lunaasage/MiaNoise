from .base import NeighborhoodScore, NoiseSource


class VenueDensity(NoiseSource):
    """Google Places API — nightlife venue density (bars, clubs, restaurants) per neighborhood."""

    source_id = "venue_density"
    weight = 0.5
    required_env_vars = ["GOOGLE_PLACES_API_KEY"]

    def fetch(self) -> list[NeighborhoodScore]:
        # Sprint 1: for each neighborhood centroid, query Google Places nearby search
        # (type=bar|night_club|restaurant), count results, normalize to 0–1.
        raise NotImplementedError("venue_density.fetch — implement in Sprint 1")
