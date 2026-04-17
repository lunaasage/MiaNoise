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

## Sprint 1 — Data Ingestion + Score Persistence

### `ingestion/db.py`

Supabase I/O layer for the ingestion pipeline. Sources and the pipeline never
construct a Supabase client directly — they import from here.

**Exports:**

- `get_client()` — reads `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`, returns a
  `supabase.Client`. Service role key is required to bypass RLS for writes.

- `seed_neighborhoods() → int` — reads `data/geojson/miami_neighborhoods.geojson`,
  computes each polygon's centroid via shapely, and upserts all 106 rows into
  `neighborhoods` (conflict on `slug`). Idempotent — safe to call on every run.

- `write_scores(composite, per_source) → str` — generates a `run_id` UUID,
  resolves neighborhood UUIDs from the DB (one `SELECT` round-trip), then bulk-inserts
  rows into `noise_scores` with `composite_score` and `source_scores` JSONB.
  Returns the `run_id` string.

- `load_neighborhood_centroids() → dict[str, tuple[float, float]]` — reads GeoJSON
  locally (no DB round-trip), returns `name → (lat, lon)`. Used by `VenueDensity`
  to avoid a DB dependency during source execution.

- `load_neighborhood_geodataframe() → GeoDataFrame` — reads GeoJSON as a WGS84
  GeoDataFrame. Used by `Complaints311` for spatial joins and by `VenueDensity`
  for circumradius computation.

**Connects to:** `ingestion/pipeline.py` (called by `run_and_persist()`),
`ingestion/sources/complaints_311.py` (calls `load_neighborhood_geodataframe()`),
`ingestion/sources/venue_density.py` (calls `load_neighborhood_centroids()` and
`load_neighborhood_geodataframe()`).

---

### `ingestion/sources/complaints_311.py` (implemented)

**Class:** `Complaints311` — `source_id="complaints_311"`, `weight=0.5`

Fetches Miami-Dade 311 noise complaints from the ArcGIS Feature Service
(`data_311_2022`) and computes a complaint-density score per neighborhood.

**`fetch()` steps:**
1. Load neighborhood polygons via `db.load_neighborhood_geodataframe()`.
2. Query ArcGIS REST endpoint (`FEATURE_SERVICE_URL`) with `where=issue_type LIKE '%NOISE%'`,
   paginating in 2000-record pages until `exceededTransferLimit` is false.
3. Drop records with null or non-numeric lat/lon.
4. Build a `GeoDataFrame` of complaint points (WGS84).
5. `gpd.sjoin(complaints, neighborhoods, predicate="within")` — spatial join.
6. `.groupby("name").size()` reindexed to all 106 neighborhoods (zeros for missing).
7. Max-normalize: `score = count / max_count`.
8. Return `list[NeighborhoodScore]` with `metadata={"raw_count": int}`.

**Env vars:** none required; `MIAMI_DATA_APP_TOKEN` optional (rate limit header).

**Connects to:** `ingestion/db.py` (`load_neighborhood_geodataframe()`),
`ingestion/sources/base.py` (inherits `NoiseSource`).

---

### `ingestion/sources/venue_density.py` (implemented)

**Class:** `VenueDensity` — `source_id="venue_density"`, `weight=0.5`

Counts nightlife venues near each neighborhood centroid using the Google Places
Nearby Search API and computes a venue-density score per neighborhood.

**`fetch()` steps:**
1. Load centroids via `db.load_neighborhood_centroids()` (name → (lat, lon)).
2. Compute per-neighborhood search radius via `_compute_radii()` (see below).
3. For each neighborhood, call `_count_places()` three times: `bar`, `night_club`, `restaurant`.
4. Sum venue counts. Max-normalize across all neighborhoods.
5. Return `list[NeighborhoodScore]` with `metadata={bar_count, club_count, restaurant_count, total}`.

**`_compute_radii()`:** Reprojects GeoJSON to UTM Zone 17N (EPSG:32617, meters),
computes each polygon's circumradius (max centroid-to-vertex distance), clips to
1500m upper bound. Miami neighborhoods range from ~300m (Brickell Key) to ~1.5km
(Allapattah) — per-neighborhood radii avoid over/undercounting.

**`_count_places()`:** Up to 3 pages per type (60 results max). Waits 2s between
paginated requests per Google's `next_page_token` requirement.

**Env vars:** `GOOGLE_PLACES_API_KEY`.

**Connects to:** `ingestion/db.py` (`load_neighborhood_centroids()`,
`load_neighborhood_geodataframe()`), `ingestion/sources/base.py`.

---

### `ingestion/pipeline.py` (updated)

Added three things to the Sprint 0 skeleton:

- `_fetch_results(active) → dict[str, list[NeighborhoodScore]]` — extracted from
  `run_pipeline()` so both `run_pipeline()` and `run_and_persist()` share the same
  fetch loop without duplication.

- `run_and_persist() → dict[str, float]` — full pipeline run with Supabase
  persistence. Seeds neighborhoods, fetches from active sources, computes scores,
  writes to `noise_scores`. Imports `ingestion.db` locally to keep `run_pipeline()`
  free of DB dependencies for testing.

- `__main__` block — `python -m ingestion.pipeline` seeds neighborhoods, runs all
  available sources, writes scores, and prints the top 10 noisiest neighborhoods.

`run_pipeline()` is **unchanged** — still pure computation, no DB side effects.

**Connects to:** `ingestion/db.py` (inside `run_and_persist()`),
`ingestion/sources/__init__.py` (`ALL_SOURCES`), `ingestion/score_engine.py`.

---

### `.env.example` (updated)

Added `SUPABASE_SERVICE_KEY` alongside the existing `SUPABASE_KEY`:
- `SUPABASE_KEY` — anon key for public reads (frontend)
- `SUPABASE_SERVICE_KEY` — service role key for backend writes (bypasses RLS)

---

## Module Dependency Map

```
pipeline.py
  ├── run_pipeline() ──────────────────────────────────────────────────────────┐
  │     └── sources/__init__.py  →  ALL_SOURCES                                │
  │           ├── complaints_311.py ──┐                                        │
  │           ├── venue_density.py   │  inherit NoiseSource / NeighborhoodScore│
  │           ├── yelp_reviews.py    ├── sources/base.py                       │
  │           ├── reddit_posts.py    │                                         │
  │           ├── tomtom_traffic.py  │                                         │
  │           ├── opensky_flights.py │                                         │
  │           └── construction.py ──┘                                         │
  │     └── score_engine.py                                                    │
  │                                                                            │
  └── run_and_persist() ─────────────────────────────────────────────────────┘
        └── db.py
              ├── seed_neighborhoods() ← data/geojson/miami_neighborhoods.geojson
              └── write_scores()       → Supabase noise_scores table

complaints_311.py  → db.load_neighborhood_geodataframe()
venue_density.py   → db.load_neighborhood_centroids()
                   → db.load_neighborhood_geodataframe()  (for radii)
```

---

## Modules Stubbed — Not Yet Implemented

| Path | Sprint | Purpose |
|---|---|---|
| `rag/` | 2 | Embedding pipeline, pgvector retrieval, profile synthesis |
| `agent/` | 3 | LangChain AgentExecutor + tools |
| `ui/app.py` | 3 | Streamlit app, Folium map, chat interface |
| `eval/` | 4 | RAGAS evaluation framework |
