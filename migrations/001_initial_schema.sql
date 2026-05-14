-- MiaNoise — initial schema
-- Run against your Supabase project via the SQL editor or supabase db push.

-- ── Extensions ────────────────────────────────────────────────────────────────

create extension if not exists "uuid-ossp";
create extension if not exists vector;          -- pgvector
create extension if not exists postgis;         -- geometry types (optional but useful for centroid queries)

-- ── neighborhoods ─────────────────────────────────────────────────────────────
-- One row per Miami neighborhood. Geometry is loaded from data/geojson/miami_neighborhoods.geojson
-- at ingestion time; centroid is derived from it.

create table if not exists neighborhoods (
    id          uuid primary key default uuid_generate_v4(),
    name        text not null unique,           -- e.g. "Wynwood Industrial District"
    slug        text not null unique,           -- e.g. "wynwood-industrial-district"
    boundary    geography(Polygon, 4326),       -- full polygon from GeoJSON
    centroid    geography(Point, 4326),         -- derived centroid for proximity queries
    created_at  timestamptz not null default now()
);

create index if not exists neighborhoods_boundary_idx on neighborhoods using gist(boundary);
create index if not exists neighborhoods_centroid_idx on neighborhoods using gist(centroid);

-- ── noise_scores ──────────────────────────────────────────────────────────────
-- One row per neighborhood per pipeline run. Preserves per-source breakdown so
-- the RAG layer can explain *why* a score is what it is.

create table if not exists noise_scores (
    id                  uuid primary key default uuid_generate_v4(),
    neighborhood_id     uuid not null references neighborhoods(id) on delete cascade,
    run_id              uuid not null,                  -- groups all scores from one pipeline run
    composite_score     float not null check (composite_score between 0 and 1),
    source_scores       jsonb not null default '{}',   -- { "complaints_311": 0.85, "venue_density": 0.90 }
    computed_at         timestamptz not null default now()
);

create index if not exists noise_scores_neighborhood_idx on noise_scores(neighborhood_id);
create index if not exists noise_scores_run_idx          on noise_scores(run_id);
create index if not exists noise_scores_computed_at_idx  on noise_scores(computed_at desc);

-- Latest score per neighborhood (used by UI and agent)
create or replace view latest_noise_scores as
select distinct on (neighborhood_id)
    ns.*,
    n.name  as neighborhood_name,
    n.slug  as neighborhood_slug
from noise_scores ns
join neighborhoods n on n.id = ns.neighborhood_id
order by neighborhood_id, computed_at desc;

-- ── reviews ───────────────────────────────────────────────────────────────────
-- Raw text corpus for the RAG pipeline. Populated by yelp_reviews and
-- reddit_posts sources (both weight=0, RAG-only). Chunked at embedding time.

create table if not exists reviews (
    id              uuid primary key default uuid_generate_v4(),
    neighborhood_id uuid references neighborhoods(id) on delete set null,
    source          text not null,              -- 'yelp' | 'reddit' | 'google'
    content         text not null,
    author          text,
    external_url    text,
    fetched_at      timestamptz not null default now(),
    metadata        jsonb not null default '{}'  -- source-specific extras (rating, upvotes, etc.)
);

create index if not exists reviews_neighborhood_idx on reviews(neighborhood_id);
create index if not exists reviews_source_idx       on reviews(source);
create index if not exists reviews_fetched_at_idx   on reviews(fetched_at desc);

-- ── embeddings ────────────────────────────────────────────────────────────────
-- Chunked review text embedded with OpenAI text-embedding-3-small (1536 dims).
-- Retrieved by the RAG pipeline via cosine similarity search.

create table if not exists embeddings (
    id              uuid primary key default uuid_generate_v4(),
    review_id       uuid not null references reviews(id) on delete cascade,
    neighborhood_id uuid references neighborhoods(id) on delete set null,  -- denormalized for fast filtering
    chunk_text      text not null,
    embedding       vector(1536) not null,      -- text-embedding-3-small output dimension
    created_at      timestamptz not null default now()
);

-- IVFFlat index for approximate nearest-neighbor search.
-- lists=100 is appropriate for a corpus of ~10k–100k chunks.
-- Recreate with a higher lists value if the corpus grows significantly.
create index if not exists embeddings_vector_idx
    on embeddings using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

create index if not exists embeddings_neighborhood_idx on embeddings(neighborhood_id);

-- ── RLS (Row Level Security) ──────────────────────────────────────────────────
-- All tables are read-only from the public anon key.
-- Writes go through the service role key (backend only).

alter table neighborhoods  enable row level security;
alter table noise_scores   enable row level security;
alter table reviews        enable row level security;
alter table embeddings     enable row level security;

create policy "public read neighborhoods"  on neighborhoods  for select using (true);
create policy "public read noise_scores"   on noise_scores   for select using (true);
create policy "public read reviews"        on reviews        for select using (true);
create policy "public read embeddings"     on embeddings     for select using (true);
