from .base import NeighborhoodScore, NoiseSource


class Complaints311(NoiseSource):
    """Miami Open Data — historical 311 noise complaints per neighborhood."""

    source_id = "complaints_311"
    weight = 0.5
    required_env_vars = []  # Miami Open Data is public; no key required for PoC

    def fetch(self) -> list[NeighborhoodScore]:
        # Sprint 1: query Miami Open Data Socrata endpoint, aggregate by neighborhood,
        # normalize complaint count to 0–1 (max-normalization), return scores.
        raise NotImplementedError("complaints_311.fetch — implement in Sprint 1")
