"""
LangChain tools for the MiaNoise conversational agent.

Three tools expose the full data layer to the Groq agent:
  - rank_neighborhoods  → composite score table with percentile context
  - get_profile         → pre-generated narrative for a specific neighborhood
  - search_reviews      → pgvector retrieval for granular noise questions

All tools are read-only. No writes happen during agent execution.
"""

import logging

from langchain.tools import tool

from ingestion.db import get_client, load_profile
from rag.retriever import retrieve

logger = logging.getLogger(__name__)


def _resolve_name(neighborhood_name: str) -> str | None:
    """
    Resolve a possibly-partial or differently-cased neighborhood name to the
    canonical DB name.

    Resolution order:
      1. Exact case-insensitive match
      2. Among partial matches (%name%), prefer the one with the most review
         embeddings — so "Brickell" picks "Brickell Village" (21 chunks) over
         "Brickell Residential District" (0 chunks) rather than alphabetical first.

    Returns the canonical name string, or None if no match found.
    """
    db = get_client()

    # 1. Exact match (case-insensitive)
    result = db.table("neighborhoods").select("name").ilike("name", neighborhood_name).execute()
    if result.data:
        return result.data[0]["name"]

    # 2. Partial match — collect all candidates
    result = db.table("neighborhoods").select("name,id").ilike("name", f"%{neighborhood_name}%").execute()
    if not result.data:
        return None

    candidates = [(r["name"], r["id"]) for r in result.data]
    if len(candidates) == 1:
        return candidates[0][0]

    # Among multiple candidates, prefer the one with the most reviews
    # (one small count query per candidate — never more than ~5 Brickell rows)
    best_name = candidates[0][0]
    best_count = -1
    for name, nbhd_id in candidates:
        count_result = (
            db.table("reviews")
            .select("id", count="exact")
            .eq("neighborhood_id", nbhd_id)
            .execute()
        )
        n = count_result.count or 0
        if n > best_count:
            best_count = n
            best_name = name

    return best_name


def _load_all_scores() -> list[dict]:
    """Fetch all rows from latest_noise_scores, sorted by composite_score desc."""
    db = get_client()
    result = (
        db.table("latest_noise_scores")
        .select("neighborhood_name,composite_score")
        .order("composite_score", desc=True)
        .execute()
    )
    return result.data or []


def _percentile_label(score: float, all_scores: list[float]) -> str:
    """
    Return 'louder than X% of Miami neighborhoods' given a score and
    the full distribution. Rounds to nearest 5 for readability.
    """
    below = sum(1 for s in all_scores if s < score)
    pct = round((below / len(all_scores)) * 100 / 5) * 5 if all_scores else 0
    return f"louder than {pct}% of Miami neighborhoods"


@tool
def rank_neighborhoods(order: str = "noisiest") -> str:
    """
    Return the top 10 Miami neighborhoods ranked by composite noise score (0.0 = silent, 1.0 = extremely loud).

    Args:
        order: 'noisiest' (highest score first, default) or 'quietest' (lowest score first)

    Use this when the user wants to find quiet or loud neighborhoods, compare areas,
    or get a ranked list. Always call this before recommending specific neighborhoods.
    """
    rows = _load_all_scores()
    if not rows:
        return "No noise score data available. The pipeline may not have run yet."

    all_scores = [r["composite_score"] for r in rows]

    if order.lower() == "quietest":
        rows = list(reversed(rows))  # ascending

    rows = rows[:10]

    lines = []
    for i, row in enumerate(rows, 1):
        name = row["neighborhood_name"]
        score = row["composite_score"]
        pct = _percentile_label(score, all_scores)
        data_note = " [limited data]" if score == 0.0 else ""
        lines.append(f"{i:2}. {name} — score {score:.2f} ({pct}){data_note}")

    header = f"{'Quietest' if order.lower() == 'quietest' else 'Noisiest'} {len(rows)} Miami neighborhoods:"
    footer = (
        "\n\nNote: [limited data] means no mapped nightlife venues or road signal was "
        "found for that neighborhood. Absence of noise sources is itself a positive signal "
        "— these areas likely have fewer bars, clubs, and complaints on record — but treat "
        "the score as a lower bound, not a verified measurement."
    )
    return header + "\n" + "\n".join(lines) + footer


@tool
def get_profile(neighborhood_name: str) -> str:
    """
    Get the pre-generated noise profile narrative for a specific Miami neighborhood.

    Args:
        neighborhood_name: the neighborhood name, e.g. 'Wynwood', 'Brickell', 'Edgewater'.
                           Use title case. If unsure of the exact name, call rank_neighborhoods
                           first to see the canonical list.

    Returns a 3–5 sentence narrative grounded in real venue reviews and noise scores.
    Use this when the user asks about a specific neighborhood by name.
    """
    canonical = _resolve_name(neighborhood_name)
    if not canonical:
        return (
            f"No neighborhood matching '{neighborhood_name}' found. "
            "Use rank_neighborhoods to see the canonical list of available neighborhoods."
        )

    profile = load_profile(canonical)
    if profile:
        return f"[{canonical}]\n\n{profile}"

    return f"No profile has been generated for '{canonical}' yet."


@tool
def search_reviews(neighborhood_name: str, query: str) -> str:
    """
    Search actual review text from bars, restaurants, and nightclubs in a neighborhood.

    Args:
        neighborhood_name: the neighborhood to search within, e.g. 'Wynwood'
        query: what you're looking for, e.g. 'noise at night', 'loud music on weekends',
               'quiet daytime', 'construction sounds'

    Returns up to 8 relevant review excerpts ordered by semantic similarity.
    Use this when the user asks a specific question about a neighborhood's noise
    character that the profile may not fully answer, or to verify a claim.
    """
    canonical = _resolve_name(neighborhood_name)
    if not canonical:
        return (
            f"No neighborhood matching '{neighborhood_name}' found. "
            "Use rank_neighborhoods to see the canonical list of available neighborhoods."
        )

    chunks = retrieve(canonical, query, top_k=8)
    if not chunks:
        return f"No review data found for '{canonical}' matching '{query}'."

    lines = [f'• "{c}"' for c in chunks]
    return (
        f"Review excerpts from {canonical} matching '{query}':\n\n"
        + "\n\n".join(lines)
    )


# Exported list for agent wiring
TOOLS = [rank_neighborhoods, get_profile, search_reviews]
