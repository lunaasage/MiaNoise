"""
RAG retrieval — pgvector cosine similarity search.

Given a neighborhood name and a query string, returns the top-k most relevant
review chunks from the embeddings table. Filters by neighborhood_id so results
are always geographically grounded.

The query is embedded with the same model used at indexing time
(text-embedding-3-small) so the vector space is consistent.
"""

import logging
import os

from openai import OpenAI

from ingestion.db import get_client

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_TOP_K = 12


def retrieve(
    neighborhood_name: str,
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> list[str]:
    """
    Return the top_k most relevant chunk_texts for a neighborhood + query.

    Args:
        neighborhood_name: e.g. "Wynwood"
        query: free-text query, e.g. "noise levels at night"
        top_k: number of chunks to return (default 12)

    Returns:
        List of chunk_text strings, ordered by cosine similarity (most similar first).
        Empty list if the neighborhood has no embeddings.
    """
    db = get_client()
    openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Resolve neighborhood name → UUID
    result = db.table("neighborhoods").select("id").eq("name", neighborhood_name).execute()
    if not result.data:
        logger.warning("retriever: no neighborhood record for %r", neighborhood_name)
        return []
    nbhd_id = result.data[0]["id"]

    # Embed the query
    resp = openai.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    query_vector = resp.data[0].embedding

    # pgvector cosine similarity via Supabase RPC
    # Requires a match_embeddings function defined in Supabase (see migrations).
    rpc_result = db.rpc(
        "match_embeddings",
        {
            "query_embedding": query_vector,
            "match_neighborhood_id": nbhd_id,
            "match_count": top_k,
        },
    ).execute()

    chunks = [row["chunk_text"] for row in rpc_result.data]
    logger.info(
        "retriever: %d chunks for %r (query=%r)", len(chunks), neighborhood_name, query[:60]
    )
    return chunks


def retrieve_multi_query(
    neighborhood_name: str,
    queries: list[str],
    top_k_per_query: int = 6,
) -> list[str]:
    """
    Run multiple queries and merge results, deduplicating by chunk_text.
    Useful for synthesis prompts that want coverage across multiple noise aspects.
    """
    seen: set[str] = set()
    results: list[str] = []
    for q in queries:
        for chunk in retrieve(neighborhood_name, q, top_k=top_k_per_query):
            if chunk not in seen:
                seen.add(chunk)
                results.append(chunk)
    return results
