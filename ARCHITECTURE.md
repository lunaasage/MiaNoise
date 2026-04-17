# MiaNoise — Architecture

## Overview

MiaNoise is a pluggable noise intelligence pipeline. Every data source is an
independent module; the pipeline discovers and runs whatever sources have valid
credentials, so the PoC (2 sources) and full version (7 sources) share the same
code without branching logic.

Data flows in one direction:

```
Sources → score_engine → pipeline → [Supabase] → RAG → Agent → UI
```

---

## Sprint 0 — Ingestion Plugin Architecture

### `ingestion/sources/base.py`

Core contracts for the entire plugin system. Nothing else in the codebase should
be imported more widely.

**Exports:**

- `NeighborhoodScore` — dataclass holding one source's reading for one neighborhood.
  Fields: `neighborhood` (str), `normalized_score` (float, validated 0–1),
  `raw_value` (float), `source_id` (str), `metadata` (dict, optional extras for RAG).

- `NoiseSource` — abstract base class every source inherits from.

  | Class variable | Purpose |
  |---|---|
  | `source_id: str` | Unique identifier, e.g. `"complaints_311"` |
  | `weight: float` | Contribution to composite score (default 1.0) |
  | `required_env_vars: list[str]` | Keys checked by `is_available()` |

  | Method | Behaviour |
  |---|---|
  | `is_available()` | Returns True if all `required_env_vars` are set; logs missing ones at DEBUG |
  | `fetch()` | Abstract — must return `list[NeighborhoodScore]` |
  | `fetch_safe()` | Pipeline entry point: calls `is_available()`, then `fetch()`. Returns `None` if unavailable. Re-raises `NotImplementedError` (unfinished stubs fail loudly). Catches all other exceptions and logs a warning so one broken source never crashes the run. |

**Connects to:** every source file (inherits), `score_engine.py` (consumes
`NeighborhoodScore`), `pipeline.py` (calls `fetch_safe()`).

---

### `ingestion/sources/__init__.py`

Source registry. The only file that knows about every source class.

**Exports:**

- `ALL_SOURCES: list[type[NoiseSource]]` — ordered list of all source classes.
  The pipeline imports this and instantiates each; sources without valid env vars
  are silently skipped via `is_available()`.
- Re-exports `NoiseSource` and `NeighborhoodScore` for convenience.

**To add a new source:** create the source file, subclass `NoiseSource`, add the
class to `ALL_SOURCES` here. No other file needs to change.

**Connects to:** `pipeline.py` (imports `ALL_SOURCES`).

---

### `ingestion/sources/complaints_311.py`

**Class:** `Complaints311`
**Source ID:** `complaints_311` | **Weight:** 0.5 | **Requires:** nothing (Miami Open Data is public)

PoC source. Will query the Miami Open Data Socrata endpoint for historical 311
noise complaints, aggregate by neighborhood, and max-normalize to 0–1.
`fetch()` raises `NotImplementedError` — implement in Sprint 1.

---

### `ingestion/sources/venue_density.py`

**Class:** `VenueDensity`
**Source ID:** `venue_density` | **Weight:** 0.5 | **Requires:** `GOOGLE_PLACES_API_KEY`

PoC source. Will query Google Places nearby search (bars, clubs, restaurants)
around each neighborhood centroid, count results, and normalize to 0–1.
`fetch()` raises `NotImplementedError` — implement in Sprint 1.

---

### `ingestion/sources/yelp_reviews.py`

**Class:** `YelpReviews`
**Source ID:** `yelp_reviews` | **Weight:** 0.0 | **Requires:** `YELP_API_KEY`

PoC source. Weight is 0 — this source feeds the RAG corpus, not the numeric
score. Will fetch business review text near each neighborhood and store it in
Supabase for embedding. `fetch()` raises `NotImplementedError` — implement in Sprint 2.

---

### `ingestion/sources/reddit_posts.py`

**Class:** `RedditPosts`
**Source ID:** `reddit_posts` | **Weight:** 0.0 | **Requires:** `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`

PoC source. Weight is 0 — RAG corpus only. Will search r/miami and r/MiamiBeach
for noise-related posts, tag them by mentioned neighborhood, and store in
Supabase. `fetch()` raises `NotImplementedError` — implement in Sprint 2.

---

### `ingestion/sources/tomtom_traffic.py`

**Class:** `TomTomTraffic`
**Source ID:** `tomtom_traffic` | **Weight:** 0.2 (placeholder) | **Requires:** `TOMTOM_API_KEY`

Full-version source. Will query TomTom Flow Segment Data for major roads per
neighborhood and derive a traffic-noise proxy. Inactive on PoC branch (key absent
→ `is_available()` returns False). `fetch()` raises `NotImplementedError`.

---

### `ingestion/sources/opensky_flights.py`

**Class:** `OpenSkyFlights`
**Source ID:** `opensky_flights` | **Weight:** 0.15 (placeholder) | **Requires:** `OPENSKY_USERNAME`, `OPENSKY_PASSWORD`

Full-version source. Will count aircraft overflights per neighborhood polygon
using the OpenSky REST API. Inactive on PoC branch. `fetch()` raises `NotImplementedError`.

---

### `ingestion/sources/construction.py`

**Class:** `ConstructionPermits`
**Source ID:** `construction_permits` | **Weight:** 0.15 (placeholder) | **Requires:** nothing (Miami Open Data is public)

Full-version source. Will query Miami Building Department permits filtered for
noise-generating work types (demolition, excavation, framing). Technically
available on PoC branch (no key required) but raises `NotImplementedError`
until Sprint 1 of the full version.

---

### `ingestion/score_engine.py`

**Exports:** `compute_composite_scores(results, active_sources) → dict[str, float]`

Accepts `results` (`source_id → list[NeighborhoodScore]`) and a list of active
source instances, and returns `neighborhood → composite score` in [0.0, 1.0].

Algorithm:
1. Build a weight map from `source.weight` for each active source.
2. Skip zero-weight sources (they feed RAG only).
3. For each source/neighborhood pair, accumulate `normalized_score × weight` and
   the running weight total.
4. Divide weighted sum by weight total per neighborhood.

Missing sources don't deflate scores — only sources that returned data contribute
to the denominator.

**Connects to:** `pipeline.py` (called after fetch loop), `ingestion/sources/base.py`
(consumes `NeighborhoodScore` and `NoiseSource` types).

---

### `ingestion/pipeline.py`

**Exports:** `run_pipeline() → dict[str, float]`

Orchestrates a full ingestion run. Does not import any source by name — all
discovery happens through `ALL_SOURCES`.

Steps:
1. Instantiate every class in `ALL_SOURCES`.
2. Filter to sources where `is_available()` is True.
3. Call `fetch_safe()` on each active source; collect non-None results.
4. Pass results to `compute_composite_scores()` and return scores.

**Connects to:** `ingestion/sources/__init__.py` (imports `ALL_SOURCES`),
`ingestion/score_engine.py` (calls `compute_composite_scores`).

---

### `requirements.txt`

Pinned dependencies for the full stack:

| Group | Packages |
|---|---|
| Core | python-dotenv, pandas, numpy |
| Geospatial | geopandas, shapely, folium |
| Database | supabase, pgvector, psycopg2-binary |
| LLM / RAG | anthropic, openai, langchain, langchain-anthropic, langchain-openai, langchain-community |
| Data sources | praw, requests |
| Frontend | streamlit, streamlit-folium, pydeck |
| Evaluation | ragas |
| Dev | pytest, pytest-asyncio |

---

### `.env.example`

Documents every environment variable consumed by the system, grouped by source.
Clarifies which sources require no key (Miami Open Data, construction permits)
vs. which activate only when their key is present. Copy to `.env` and fill in
credentials before running.

---

### `migrations/001_initial_schema.sql`

Initial Supabase DDL. Run once via the Supabase SQL editor or `supabase db push`.

**Enables extensions:** `uuid-ossp`, `vector` (pgvector), `postgis`.

**Creates four tables:**

| Table | Purpose |
|---|---|
| `neighborhoods` | One row per Miami neighborhood. Stores name, slug, PostGIS `boundary` polygon (EPSG:4326), and derived `centroid`. Spatial indexes on both geography columns. |
| `noise_scores` | One row per neighborhood per pipeline run. Stores `composite_score` (float, 0–1), `source_scores` (JSONB breakdown by source), and `run_id` (UUID grouping all scores from one run). |
| `reviews` | Raw text corpus for RAG. Populated by `yelp_reviews` and `reddit_posts` sources. Fields: `source`, `content`, `author`, `external_url`, `metadata` (JSONB). |
| `embeddings` | Chunked review text with 1536-dim pgvector embeddings (OpenAI text-embedding-3-small). IVFFlat index (`lists=100`) for approximate cosine similarity search. `neighborhood_id` is denormalized here for fast filtered retrieval. |

**Creates one view:** `latest_noise_scores` — `DISTINCT ON (neighborhood_id)` ordered by `computed_at DESC`, joined with neighborhood name/slug. Used by the UI and agent.

**RLS:** All four tables have Row Level Security enabled. Public anon key gets `SELECT` only; writes require the service role key (backend pipeline).

**Connects to:** `ingestion/pipeline.py` (writes `noise_scores`), `rag/` (reads/writes `reviews` and `embeddings`), `ui/app.py` (reads `latest_noise_scores` view).

---

### `data/geojson/miami_neighborhoods.geojson`

106 Miami neighborhood polygons sourced from the City of Miami ArcGIS Hub (EPSG:4326). All features are `Polygon` type. Each feature has a `name` property (e.g. `"Wynwood Industrial District"`) used to join against the `neighborhoods` table.

**Loaded at:** first pipeline run to seed the `neighborhoods` table (Sprint 1).

**Connects to:** `ingestion/pipeline.py` (reads boundaries to seed DB), `ui/app.py` (renders choropleth overlay on Folium map), `migrations/001_initial_schema.sql` (`neighborhoods.boundary` column stores these geometries).

---

## Module Dependency Map

```
pipeline.py
  └── sources/__init__.py  →  ALL_SOURCES
        ├── complaints_311.py   ──┐
        ├── venue_density.py     │
        ├── yelp_reviews.py      │  all inherit from
        ├── reddit_posts.py      ├── sources/base.py
        ├── tomtom_traffic.py    │    (NoiseSource, NeighborhoodScore)
        ├── opensky_flights.py   │
        └── construction.py    ──┘
  └── score_engine.py
        └── sources/base.py  (NeighborhoodScore, NoiseSource types)
```

---

## Modules Stubbed — Not Yet Implemented

| Path | Sprint | Purpose |
|---|---|---|
| `rag/` | 2 | Embedding pipeline, pgvector retrieval, profile synthesis |
| `agent/` | 3 | LangChain AgentExecutor + tools |
| `ui/app.py` | 3 | Streamlit app, Folium map, chat interface |
| `eval/` | 4 | RAGAS evaluation framework |
