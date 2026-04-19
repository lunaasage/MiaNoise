"""
Neighborhood noise profile synthesis.

Combines:
  - Composite noise score (0–1) and per-source breakdown from the DB
  - Top retrieved review chunks (from rag/retriever.py)
  - Claude claude-sonnet-4-20250514 for natural-language synthesis

Entry point: generate_profile(neighborhood_name) → str narrative

The prompt is designed so Claude can only claim things the retrieved text
or numeric scores actually support. No hallucination of venues, hours, or
specific addresses — the narrative is grounded in what's in the chunks.
"""

import logging
import os

import anthropic

from ingestion.db import get_client
from rag.retriever import retrieve_multi_query

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 512

SYNTHESIS_QUERIES = [
    "noise levels at night",
    "loud music bars clubs nightlife",
    "quiet peaceful daytime",
    "construction traffic street noise",
    "weekend party crowd atmosphere",
]

SYSTEM_PROMPT = """You are a neighborhood noise intelligence analyst for Miami renters.
Your job is to write a concise, grounded noise profile for a Miami neighborhood based on:
1. A composite noise score (0.0 = silent, 1.0 = extremely loud)
2. Scores from specific data sources
3. Actual review excerpts from bars, nightclubs, and restaurants in the area

Rules:
- Only describe noise patterns that are supported by the provided reviews or scores
- Be specific about timing (nights, weekends, daytime) when the reviews support it
- Do not invent venue names, street names, or hours not present in the reviews
- Write in plain language suitable for a renter making a housing decision
- Aim for 3–5 sentences. No bullet points. No headers."""


def _load_latest_scores(neighborhood_name: str) -> dict:
    """Return composite_score and source_scores for the most recent pipeline run."""
    db = get_client()
    result = (
        db.table("latest_noise_scores")
        .select("composite_score,source_scores")
        .eq("neighborhood_name", neighborhood_name)
        .execute()
    )
    if not result.data:
        return {"composite_score": None, "source_scores": {}}
    return result.data[0]


def _build_prompt(
    neighborhood: str,
    composite_score: float | None,
    source_scores: dict,
    chunks: list[str],
) -> str:
    score_str = f"{composite_score:.2f}" if composite_score is not None else "unknown"

    source_lines = []
    if source_scores.get("osm_venues") is not None:
        source_lines.append(f"  - Venue density score: {source_scores['osm_venues']:.2f}")
    if source_scores.get("osm_roads") is not None:
        source_lines.append(f"  - Road traffic noise score: {source_scores['osm_roads']:.2f}")
    source_block = "\n".join(source_lines) if source_lines else "  (no per-source breakdown)"

    chunk_block = "\n\n".join(f'"{c}"' for c in chunks) if chunks else "(no review data available)"

    return f"""Neighborhood: {neighborhood}
Composite noise score: {score_str} / 1.0 (higher = louder)
{source_block}

Review excerpts from venues in this neighborhood:
{chunk_block}

Write a noise profile for {neighborhood} that a renter would find useful."""


def generate_profile(neighborhood_name: str) -> str:
    """
    Generate a natural-language noise profile for a neighborhood.

    Retrieves scores from the DB and review chunks via pgvector, then calls
    Claude to synthesize a grounded narrative.

    Returns the profile text, or a fallback string if data is insufficient.
    """
    scores = _load_latest_scores(neighborhood_name)
    composite = scores.get("composite_score")
    source_scores = scores.get("source_scores") or {}

    chunks = retrieve_multi_query(
        neighborhood_name,
        SYNTHESIS_QUERIES,
        top_k_per_query=5,
    )

    if not chunks and composite is None:
        return (
            f"{neighborhood_name} does not have sufficient data for a noise profile. "
            "It may be a quiet residential area with few mapped venues."
        )

    prompt = _build_prompt(neighborhood_name, composite, source_scores, chunks)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    profile = response.content[0].text.strip()

    logger.info(
        "synthesizer: generated profile for %r (%d chunks, score=%.2f)",
        neighborhood_name,
        len(chunks),
        composite or 0.0,
    )
    return profile


if __name__ == "__main__":
    import logging
    from dotenv import load_dotenv

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    load_dotenv()

    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "Wynwood"
    profile = generate_profile(name)
    print(f"\n=== {name} Noise Profile ===\n")
    print(profile)
