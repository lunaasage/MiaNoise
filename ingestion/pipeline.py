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
from ingestion.sources.base import CorpusDocument, NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)


def _fetch_results(
    active: list[NoiseSource],
) -> dict[str, list[NeighborhoodScore]]:
    """Fetch from scoring sources. Only collects list[NeighborhoodScore] results."""
    results: dict[str, list[NeighborhoodScore]] = {}
    for source in active:
        readings = source.fetch_safe()
        if readings is not None and readings and isinstance(readings[0], NeighborhoodScore):
            results[source.source_id] = readings
    return results


def _fetch_corpus(
    active: list[NoiseSource],
) -> list[CorpusDocument]:
    """Fetch from corpus sources. Collects and flattens list[CorpusDocument] results."""
    documents: list[CorpusDocument] = []
    for source in active:
        results = source.fetch_safe()
        if results is not None and results and isinstance(results[0], CorpusDocument):
            documents.extend(results)
    return documents


def _split_by_role(
    active: list[NoiseSource],
) -> tuple[list[NoiseSource], list[NoiseSource]]:
    """Split active sources into (scoring, corpus) lists based on source_role."""
    scoring = [s for s in active if s.source_role in ("scoring", "both")]
    corpus  = [s for s in active if s.source_role in ("corpus",  "both")]
    return scoring, corpus


def run_pipeline() -> dict[str, float]:
    """
    Run the ingestion pipeline without any DB writes.
    Returns neighborhood → composite score (0–1).
    Safe to call in tests and scripts that don't need persistence.
    """
    sources = [cls() for cls in ALL_SOURCES]
    active  = [s for s in sources if s.is_available()]

    if not active:
        logger.warning("No sources available — check your .env")
        return {}

    scoring, corpus = _split_by_role(active)
    logger.info("Scoring sources: %s", [s.source_id for s in scoring])
    logger.info("Corpus sources:  %s", [s.source_id for s in corpus])

    scoring_results = _fetch_results(scoring)
    return compute_composite_scores(scoring_results, scoring)


def run_and_persist() -> dict[str, float]:
    """
    Full pipeline run with Supabase persistence.

    Steps:
      1. Seed neighborhoods table from GeoJSON (idempotent upsert)
      2. Fetch scoring sources → compute composite scores → write to noise_scores
      3. Fetch corpus sources → log results (Sprint 2 will write to reviews table)
      4. Return composite scores

    Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in the environment.
    """
    from ingestion import db

    db.seed_neighborhoods()

    sources = [cls() for cls in ALL_SOURCES]
    active  = [s for s in sources if s.is_available()]

    if not active:
        logger.warning("No sources available — check your .env")
        return {}

    scoring, corpus = _split_by_role(active)
    logger.info("Scoring sources: %s", [s.source_id for s in scoring])
    logger.info("Corpus sources:  %s", [s.source_id for s in corpus])

    scoring_results = _fetch_results(scoring)
    composite = compute_composite_scores(scoring_results, scoring)

    per_source = {
        source_id: {r.neighborhood: r.normalized_score for r in readings}
        for source_id, readings in scoring_results.items()
    }
    db.write_scores(composite, per_source)

    documents = _fetch_corpus(corpus)
    if documents:
        written = db.write_corpus(documents)
        logger.info(
            "Corpus: wrote %d review documents from %d corpus source(s)",
            written,
            len(corpus),
        )

    from rag.synthesizer import generate_all_profiles
    generate_all_profiles()

    return composite


if __name__ == "__main__":
    import logging
    from dotenv import load_dotenv

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    load_dotenv()
    scores = run_and_persist()
    print(f"\nTop 10 noisiest neighborhoods:")
    for name, score in sorted(scores.items(), key=lambda x: -x[1])[:10]:
        print(f"  {score:.3f}  {name}")
