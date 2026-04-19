"""
Chunking and embedding for the RAG pipeline.

Strategy: each review row is treated as one chunk. Reviews from Google Places
are already short (50–300 words), so splitting further would break sentence
coherence and lose venue context. The venue/neighborhood prefix embedded by
GooglePlacesReviews.fetch() gives the embedding geographic anchoring without
needing a separate metadata filter at retrieval time.

Embeds with OpenAI text-embedding-3-small (1536 dims). Writes to the
embeddings table, denormalizing neighborhood_id for fast per-neighborhood
similarity searches.

Entry points:
  embed_all()           — embed every review not yet in embeddings table
  embed_neighborhood()  — embed reviews for a single neighborhood (useful for testing)
"""

import logging
import os
import time
from typing import Iterator

from openai import OpenAI

from ingestion.db import get_client

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBED_BATCH_SIZE = 100   # OpenAI allows up to 2048 inputs per request; 100 is safe
RETRY_SLEEP_S = 5


def _get_openai() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _fetch_all_pages(client, table: str, select: str, filters: dict | None = None) -> list[dict]:
    """
    Paginate a Supabase table query until all rows are fetched.
    Builds a fresh query per page to avoid Supabase SDK param accumulation bug
    that occurs when calling .range() on the same query object multiple times.
    """
    PAGE = 1000
    results = []
    offset = 0
    while True:
        q = client.table(table).select(select)
        for col, val in (filters or {}).items():
            q = q.eq(col, val)
        batch = q.range(offset, offset + PAGE - 1).execute().data
        results.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return results


def _iter_unembedded_reviews(
    client, neighborhood_id: str | None = None
) -> Iterator[dict]:
    """
    Yield reviews that don't yet have a corresponding embeddings row.
    Paginates both queries to handle > 1000 rows (Supabase PostgREST default limit).
    """
    filters = {"neighborhood_id": neighborhood_id} if neighborhood_id else {}

    embedded_ids = {
        r["review_id"]
        for r in _fetch_all_pages(client, "embeddings", "review_id", filters)
    }
    all_reviews = _fetch_all_pages(client, "reviews", "id,neighborhood_id,content", filters)

    for row in all_reviews:
        if row["id"] not in embedded_ids:
            yield row


def _embed_batch(openai_client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts, with one retry on rate-limit errors."""
    try:
        resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in resp.data]
    except Exception as exc:
        if "rate" in str(exc).lower():
            logger.warning("embedder: rate limit hit, sleeping %ds", RETRY_SLEEP_S)
            time.sleep(RETRY_SLEEP_S)
            resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
            return [item.embedding for item in resp.data]
        raise


def _write_embeddings(client, rows: list[dict]) -> None:
    client.table("embeddings").insert(rows).execute()


def embed_all() -> int:
    """Embed all reviews not yet embedded. Returns total chunks written."""
    db = get_client()
    openai = _get_openai()

    reviews = list(_iter_unembedded_reviews(db))
    if not reviews:
        logger.info("embedder: nothing to embed (all reviews already embedded)")
        return 0

    logger.info("embedder: embedding %d reviews", len(reviews))
    total = _embed_reviews(db, openai, reviews)
    logger.info("embedder: wrote %d embedding rows", total)
    return total


def embed_neighborhood(neighborhood_name: str) -> int:
    """Embed reviews for a single neighborhood. Returns chunks written."""
    db = get_client()
    openai = _get_openai()

    # Resolve name → UUID
    result = db.table("neighborhoods").select("id").eq("name", neighborhood_name).execute()
    if not result.data:
        logger.error("embedder: no neighborhood record for %r", neighborhood_name)
        return 0
    nbhd_id = result.data[0]["id"]

    reviews = list(_iter_unembedded_reviews(db, neighborhood_id=nbhd_id))
    if not reviews:
        logger.info("embedder: no unembedded reviews for %r", neighborhood_name)
        return 0

    logger.info(
        "embedder: embedding %d reviews for %r", len(reviews), neighborhood_name
    )
    total = _embed_reviews(db, openai, reviews)
    logger.info("embedder: wrote %d embedding rows for %r", total, neighborhood_name)
    return total


def _embed_reviews(db, openai: OpenAI, reviews: list[dict]) -> int:
    total = 0
    for i in range(0, len(reviews), EMBED_BATCH_SIZE):
        batch = reviews[i : i + EMBED_BATCH_SIZE]
        texts = [r["content"] for r in batch]
        vectors = _embed_batch(openai, texts)
        rows = [
            {
                "review_id": r["id"],
                "neighborhood_id": r["neighborhood_id"],
                "chunk_text": r["content"],
                "embedding": vec,
            }
            for r, vec in zip(batch, vectors)
        ]
        _write_embeddings(db, rows)
        total += len(rows)
        logger.debug("embedder: batch %d/%d done", i // EMBED_BATCH_SIZE + 1, -(-len(reviews) // EMBED_BATCH_SIZE))
    return total


if __name__ == "__main__":
    import logging
    from dotenv import load_dotenv

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    load_dotenv()
    embed_all()
