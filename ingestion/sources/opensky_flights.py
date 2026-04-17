from .base import NeighborhoodScore, NoiseSource


class OpenSkyFlights(NoiseSource):
    """OpenSky Network — overflight frequency over Miami neighborhoods."""

    source_id = "opensky_flights"
    weight = 0.15  # placeholder — calibrate once all full-version sources are active
    required_env_vars = ["OPENSKY_USERNAME", "OPENSKY_PASSWORD"]

    def fetch(self) -> list[NeighborhoodScore]:
        # Full version: query OpenSky REST API for flight state vectors over Miami bounding
        # box, count overflights per neighborhood polygon, normalize to 0–1.
        raise NotImplementedError("opensky_flights.fetch — full version, not in PoC")
