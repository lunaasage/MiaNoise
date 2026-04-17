"""
Composite noise score computation.

Accepts per-source results and applies weighted averaging to produce a single
0–1 score per neighborhood. Weights come from each source's class-level `weight`
attribute and are re-normalized against only the sources that returned data, so
missing sources don't deflate scores for present ones.
"""

import logging
from collections import defaultdict

from ingestion.sources.base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)


def compute_composite_scores(
    results: dict[str, list[NeighborhoodScore]],
    active_sources: list[NoiseSource],
) -> dict[str, float]:
    """
    Compute weighted composite noise score per neighborhood.

    Args:
        results: source_id → list[NeighborhoodScore] for sources that returned data
        active_sources: source instances used to look up weights

    Returns:
        neighborhood → composite score in [0.0, 1.0]
    """
    weight_map = {s.source_id: s.weight for s in active_sources}

    weighted_sum: dict[str, float] = defaultdict(float)
    weight_total: dict[str, float] = defaultdict(float)

    for source_id, readings in results.items():
        w = weight_map.get(source_id, 1.0)
        if w == 0.0:
            # Zero-weight sources feed RAG only — don't affect the numeric score.
            continue
        for reading in readings:
            weighted_sum[reading.neighborhood] += reading.normalized_score * w
            weight_total[reading.neighborhood] += w

    if not weighted_sum:
        logger.warning("score_engine: no weighted readings — returning empty scores")
        return {}

    scores = {
        nbhd: weighted_sum[nbhd] / weight_total[nbhd]
        for nbhd in weighted_sum
        if weight_total[nbhd] > 0
    }

    logger.info(
        "Computed scores for %d neighborhoods from %d source(s)",
        len(scores),
        len(results),
    )
    return scores
