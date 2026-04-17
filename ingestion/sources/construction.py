from .base import NeighborhoodScore, NoiseSource


class ConstructionPermits(NoiseSource):
    """Miami Open Data — active construction permit locations per zone."""

    source_id = "construction_permits"
    weight = 0.15  # placeholder — calibrate once all full-version sources are active
    required_env_vars = []  # Miami Open Data is public

    def fetch(self) -> list[NeighborhoodScore]:
        # Full version: query Miami Building Department permit dataset, filter for active
        # permits with work type that generates noise (demolition, excavation, framing),
        # count per neighborhood, normalize to 0–1.
        raise NotImplementedError("construction_permits.fetch — full version, not in PoC")
