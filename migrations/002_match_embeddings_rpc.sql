-- Sprint 2: pgvector similarity search RPC
-- Run this in the Supabase SQL editor after 001_initial_schema.sql

-- match_embeddings: returns the top match_count embedding chunks for a neighborhood,
-- ordered by cosine similarity to query_embedding.
-- Called by rag/retriever.py via db.rpc("match_embeddings", {...}).

create or replace function match_embeddings(
    query_embedding    vector(1536),
    match_neighborhood_id uuid,
    match_count        int default 12
)
returns table (
    id              uuid,
    review_id       uuid,
    neighborhood_id uuid,
    chunk_text      text,
    similarity      float
)
language sql stable
as $$
    select
        e.id,
        e.review_id,
        e.neighborhood_id,
        e.chunk_text,
        1 - (e.embedding <=> query_embedding) as similarity
    from embeddings e
    where e.neighborhood_id = match_neighborhood_id
    order by e.embedding <=> query_embedding
    limit match_count;
$$;
