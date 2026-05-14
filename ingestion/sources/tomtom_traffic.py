from .base import NeighborhoodScore, NoiseSource


class TomTomTraffic(NoiseSource):
    """TomTom Traffic API — road traffic volume as a proxy for traffic noise."""

    source_id = "tomtom_traffic"
    source_role = "scoring"
    weight = 0.2  # placeholder — calibrate once all full-version sources are active
    required_env_vars = ["TOMTOM_API_KEY"]

    def fetch(self) -> list[NeighborhoodScore]:
        # Full version: query TomTom Flow Segment Data for major roads per neighborhood,
        # aggregate current/freeflow ratio, normalize to 0–1.
        raise NotImplementedError("tomtom_traffic.fetch — full version, not in PoC")
