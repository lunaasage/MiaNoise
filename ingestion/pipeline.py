"""
Ingestion pipeline orchestrator.

Discovers all registered sources, checks availability, fetches data from active
ones, and returns composite noise scores. Never imports a specific source by name —
all sources are discovered through the ALL_SOURCES registry so adding a new source
requires no changes here.
"""

import logging

from ingestion.score_engine import compute_composite_scores
from ingestion.sources import ALL_SOURCES

logger = logging.getLogger(__name__)


def run_pipeline() -> dict[str, float]:
    """
    Run the full ingestion pipeline.

    Returns:
        neighborhood → composite noise score in [0.0, 1.0]
    """
    sources = [cls() for cls in ALL_SOURCES]
    active = [s for s in sources if s.is_available()]

    if not active:
        logger.warning("No sources available — check your .env")
        return {}

    logger.info("Active sources: %s", [s.source_id for s in active])

    results: dict = {}
    for source in active:
        readings = source.fetch_safe()
        if readings is not None:
            results[source.source_id] = readings

    return compute_composite_scores(results, active)
