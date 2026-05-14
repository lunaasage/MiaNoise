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

**Class:** `Complaints311` — `source_id="complaints_311"`, `weight=0.3`

Fetches City of Miami 311 NOISEVIO service requests from the last 12 months
and computes a complaint-density score per neighborhood.

**`fetch()` steps:**
1. Load neighborhood polygons via `db.load_neighborhood_geodataframe()`.
2. Query the City of Miami ArcGIS Feature Service (`services1.arcgis.com/CvuPhqcTQpZPT9qY/...`),
   filtering for `issue_type = 'NOISEVIO'` AND `ticket_created_date_time >= (now - 365 days)`.
   Paginate in 2000-record pages.
3. Drop records with null or non-numeric lat/lon.
4. Build a `GeoDataFrame` of complaint points (WGS84).
5. `gpd.sjoin(complaints, neighborhoods, predicate="within")` — spatial join.
6. `.groupby("name").size()` reindexed to all 106 neighborhoods (zeros for missing).
7. Max-normalize: `score = count / max_count`.
8. Return `list[NeighborhoodScore]` with `metadata={"raw_count": int}`.

**Why City of Miami (not Miami-Dade):** Miami-Dade County 311 datasets contain
only waste/infrastructure requests — no noise category. City of Miami covers the
exact target neighborhoods (Wynwood, Brickell, Little Havana, lat ~25.73–25.85).

**Env vars:** none required.

**Connects to:** `ingestion/db.py` (`load_neighborhood_geodataframe()`),
`ingestion/sources/base.py` (inherits `NoiseSource`).

---

### `ingestion/sources/osm_venues.py`

**Class:** `OSMVenueDensity` — `source_id="osm_venues"`, `weight=0.5`

Bar/nightclub/restaurant density per neighborhood via OSM Overpass API.
No API key required; returns every mapped venue in Miami (~3–5× more complete
than Google Places, which caps at 20 results per type per query).

**`fetch()` steps:**
1. Load neighborhood polygons via `db.load_neighborhood_geodataframe()`.
2. Compute bounding box with 0.01° padding; POST Overpass query for
   `amenity~"^(bar|nightclub|restaurant)$"` nodes and ways.
3. Extract lat/lon: nodes directly, ways via `center` coords.
4. Spatial join points to neighborhoods.
5. Count per neighborhood, max-normalize, return `list[NeighborhoodScore]`.

**Env vars:** none.

**Connects to:** `ingestion/db.py`, `ingestion/sources/base.py`.

---

### `ingestion/sources/osm_roads.py`

**Class:** `OSMRoadNoise` — `source_id="osm_roads"`, `weight=0.2`

Weighted road-km per neighborhood as a traffic noise proxy via OSM Overpass.
No API key required; replaces TomTom/FDOT for the PoC.

**Score:** `sum(clipped_length_m × road_weight)` per neighborhood, max-normalized.
Road weights: motorway×3.0, trunk×2.0, primary×1.0 (reflecting ~dB contribution).

**`fetch()` steps:**
1. Load neighborhoods; compute bounding box.
2. POST Overpass query for `highway~"^(motorway|trunk|primary|...)"`, requesting full geometry.
3. Build `GeoDataFrame` of `LineString` geometries with `road_weight` column.
4. Reproject both layers to UTM Zone 17N (EPSG:32617) for metric accuracy.
5. `gpd.overlay(how="intersection")` clips road segments to neighborhood polygons.
6. `geometry.length` × `road_weight` → sum per neighborhood → max-normalize.

**Env vars:** none.

**Connects to:** `ingestion/db.py`, `ingestion/sources/base.py`.

---

### `ingestion/sources/venue_density.py` (Sprint 2 enrichment)

**Class:** `VenueDensity` — `source_id="venue_density"`, `weight=0.0`

Google Places API (New) venue density. Weight is 0 — `OSMVenueDensity` is the
primary venue scorer for PoC. This source activates in Sprint 2 for cross-validation
and enrichment when `GOOGLE_PLACES_API_KEY` is present.

**Env vars:** `GOOGLE_PLACES_API_KEY`.

**Connects to:** `ingestion/db.py`, `ingestion/sources/base.py`.

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
  │           ├── osm_venues.py      │  inherit NoiseSource / NeighborhoodScore│
  │           ├── osm_roads.py       ├── sources/base.py                       │
  │           ├── venue_density.py   │                                         │
  │           ├── yelp_reviews.py    │                                         │
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
osm_venues.py      → db.load_neighborhood_geodataframe()
osm_roads.py       → db.load_neighborhood_geodataframe()
venue_density.py   → db.load_neighborhood_centroids()
                   → db.load_neighborhood_geodataframe()  (for radii)
```

---

---

## Sprint 2 — RAG Pipeline

### `ingestion/sources/base.py` (updated)

Added `CorpusDocument` dataclass alongside `NeighborhoodScore`:

- `CorpusDocument` — fields: `neighborhood`, `source_id`, `content` (raw text), `author`, `external_url`, `metadata`. Returned by corpus sources instead of `NeighborhoodScore`.
- `fetch()` return type updated to `list[NeighborhoodScore] | list[CorpusDocument]`.
- `source_role` ClassVar (`"scoring"` | `"corpus"` | `"both"`) routes pipeline output.

---

### `ingestion/sources/google_places_reviews.py`

**Class:** `GooglePlacesReviews` — `source_id="google_places"`, `source_role="corpus"`

Primary corpus source for the RAG pipeline. Fetches review text for bars, nightclubs, and restaurants near each neighborhood with OSM-mapped venues.

**`fetch()` steps:**
1. Load OSM venue cache to identify the 59 neighborhoods with venues (avoids querying all 104).
2. For each neighborhood, search Google Places API (New) for `bar`, `night_club`, `restaurant` within UTM circumradius (capped 1500m).
3. For each place, collect up to 5 reviews. Prepend `[Venue Name, Neighborhood]` to each review for geographic anchoring in the embedding space.
4. Return `list[CorpusDocument]`.

**Result:** 10,095 review documents across 58 neighborhoods. Average noise keyword hit rate 63%.

**Env vars:** `GOOGLE_PLACES_API_KEY`.

---

### `ingestion/db.py` (updated)

Added `write_corpus(documents: list[CorpusDocument]) → int` — resolves neighborhood UUIDs, bulk-inserts into the `reviews` table. Returns rows written.

---

### `ingestion/pipeline.py` (updated)

Added `_fetch_corpus(active) → list[CorpusDocument]` alongside `_fetch_results`. `run_and_persist()` now calls `db.write_corpus()` after fetching corpus sources.

---

### `migrations/002_match_embeddings_rpc.sql`

Defines `match_embeddings(query_embedding, match_neighborhood_id, match_count)` — pgvector cosine similarity function called by `rag/retriever.py` via Supabase RPC. Filters by `neighborhood_id` before ranking so results are always geographically scoped.

---

### `rag/embedder.py`

**Entry points:** `embed_all()`, `embed_neighborhood(name)`

Embeds review text with OpenAI `text-embedding-3-small` (1536 dims). Strategy: one review = one chunk. Reviews are already short (50–300 words); splitting further would break sentence coherence and lose venue context already prepended by the corpus source.

Paginates Supabase queries (1000 rows/page) for both the already-embedded ID set and the reviews table. Idempotent — skips reviews already in the embeddings table.

**Connects to:** `ingestion/db.py` (Supabase client), OpenAI API.

---

### `rag/retriever.py`

**Entry points:** `retrieve(neighborhood, query, top_k)`, `retrieve_multi_query(neighborhood, queries, top_k_per_query)`

Embeds the query with the same model used at indexing time, then calls `match_embeddings()` RPC for neighborhood-filtered cosine similarity search. `retrieve_multi_query` runs multiple queries (noise at night, loud music, quiet daytime, etc.) and merges results with deduplication by exact chunk text.

**Connects to:** `ingestion/db.py`, OpenAI API, Supabase RPC.

---

### `rag/synthesizer.py`

**Entry point:** `generate_profile(neighborhood_name) → str`

Loads latest composite + per-source scores from `latest_noise_scores` view, retrieves top chunks via `retrieve_multi_query`, and calls OpenAI GPT-4o-mini with a grounding prompt that restricts the model to only describing noise patterns supported by the retrieved text or scores.

Returns a 3–5 sentence natural-language noise profile suitable for a renter.

**Model:** `gpt-4o-mini` (OpenAI). Anthropic removed from stack — OpenAI consolidates embeddings and synthesis under one provider at lower cost.

**Connects to:** `ingestion/db.py`, `rag/retriever.py`, OpenAI API.

---

## Sprint 3 — Conversational Agent + UI

### `migrations/003_profiles_table.sql`

Creates the `profiles` table and `latest_profiles` view.

- `profiles` — `(id, neighborhood_id, profile_text, model, generated_at)`. One row per generation run per neighborhood; the view selects the most recent via `DISTINCT ON (neighborhood_id) ORDER BY generated_at DESC`.
- `latest_profiles` view — joins with `neighborhoods` to expose `neighborhood_name` and `neighborhood_slug` alongside `profile_text`. Read by the UI for click-to-profile (zero API cost per page load).
- RLS: public read enabled; writes require service role key.

**Connects to:** `ingestion/db.py` (`write_profile`, `load_profile`, `load_all_profiles`), `ui/app.py`.

---

### `rag/synthesizer.py` (updated)

Added `generate_all_profiles() → int` alongside `generate_profile(name)`.

Iterates the `neighborhoods` table directly (all 104 rows) rather than the `reviews` table. Neighborhoods with venue reviews get full RAG-grounded profiles; data-sparse residential neighborhoods get score-only profiles derived from `composite_score` and `source_scores`. Returns count of profiles written.

Called from `pipeline.run_and_persist()` after `embed_all()`.

---

### `ingestion/db.py` (updated)

Added five UI-facing read functions:

| Function | Returns | Used by |
|---|---|---|
| `write_profile(name, text, model)` | — | `synthesizer.generate_all_profiles()` |
| `load_profile(name) → str \| None` | Latest profile text for one neighborhood | `ui/app.py` click-to-profile |
| `load_all_profiles() → list[dict]` | `[{neighborhood_name, profile_text}]` for all neighborhoods | Profiles tab |
| `load_neighborhood_reviews(name) → list[str]` | All review texts for one neighborhood | Compare & Temporal tab |
| `load_latest_scores() → dict[str, float]` | `{name: composite_score}` from `latest_noise_scores` view | Map choropleth + metrics |

---

### `agent/agent.py`

LangChain 1.x conversational agent backed by OpenAI `gpt-4o-mini`.

**Entry points:**
- `get_agent()` — builds and returns a `CompiledStateGraph` (LangChain 1.x `create_agent`). Called once at app startup; cached via `@st.cache_resource`.
- `ask(agent, user_input, history) → (reply_text, updated_history)` — sends one turn. `history` is the full LangChain message list (HumanMessage, AIMessage, tool call/result intermediates); returned `updated_history` is passed back on the next call to preserve multi-turn context.

**LLM choice:** Started with Groq Llama 3.3 70B (free tier). Hit the 100K-tokens/day cap in 15–20 questions — agent loops re-send full context (~5–7K tokens/question). Switched to `gpt-4o-mini`; consolidates on the existing OpenAI provider, pennies at PoC scale, far higher rate limits. See `tasks/lessons.md` L16.

**System prompt enforces:**
- `get_profile` always called first for neighborhood-specific questions
- `search_reviews` called on the same turn for timing-qualified questions
- `rank_neighborhoods` only for multi-neighborhood ranking queries
- Answers cite composite score; no invented venue names or hours

**Error handling:** `RateLimitError` and `GraphRecursionError` surface as user-readable messages rather than tracebacks.

**Connects to:** `agent/tools.py`, `langchain_openai.ChatOpenAI`, `agent/executor.py`.

---

### `agent/tools.py`

Three LangChain tools registered as `TOOLS`:

| Tool | Input | What it does |
|---|---|---|
| `rank_neighborhoods` | `top_n`, `order` ("loudest"/"quietest") | Reads `latest_noise_scores` view, returns ranked list with scores and labels |
| `get_profile` | `neighborhood_name` | Resolves name via `_resolve_name()`, loads profile from `latest_profiles` |
| `search_reviews` | `neighborhood_name`, `query` | Runs `rag.retriever.retrieve_multi_query()`, returns top review excerpts |

**`_resolve_name(name)`:** exact match → case-insensitive partial match → rank by review count. Fixes "Brickell" resolving to the wrong Brickell sub-neighborhood.

**Connects to:** `ingestion/db.py`, `rag/retriever.py`.

---

### `agent/executor.py`

Thin re-export facade:

```python
from agent.agent import ask, get_agent
```

The UI imports only from here. Agent internals (`agent.py`, `tools.py`) can change without touching `ui/app.py`.

---

### `ui/map_builder.py`

**Entry point:** `build_map(gdf: GeoDataFrame) → folium.Map`

Builds a Folium choropleth map from a GeoDataFrame with `name`, `geometry`, and `composite_score` columns.

- Base tiles: CartoDB Positron (clean, no visual noise).
- Colormap: `branca.LinearColormap` green → yellow → red, vmin=0 vmax=1.
- `GeoJson` layer with `style_function` (fillColor from colormap) and `highlight_function` (darker border on hover).
- `GeoJsonTooltip` shows neighborhood name and score percentage.
- Colormap legend added to map.

**Connects to:** `ui/app.py`, `folium`, `branca`.

---

### `ui/app.py`

Four-tab Streamlit dashboard. Entry point: `streamlit run ui/app.py` from project root.

**Shared data loading (cached):**
- `_scores()` — `@st.cache_data(ttl=3600)` — `load_latest_scores()` → score dict
- `_gdf()` — `@st.cache_data(ttl=86400)` — GeoDataFrame from GeoJSON
- `_all_profiles()` — `@st.cache_data(ttl=3600)` — all profiles as list of dicts
- `_profile(name)` — `@st.cache_data(ttl=300)` — single profile for click-to-profile
- `_reviews(name)` — `@st.cache_data(ttl=3600)` — review texts for temporal analysis
- `_agent()` — `@st.cache_resource` — LangChain agent (built once, shared across reruns)

**Tab 1 — Map:** Folium choropleth via `st_folium`. Click → point-in-polygon lookup (`shapely.Point.within`) → `st.session_state.selected` → profile loaded from DB. Quicklinks to top-5 loudest neighborhoods when nothing is selected.

**Tab 2 — Neighborhood Profiles:** Text search + noise-level dropdown filter + sort (loudest/quietest/A→Z). Results as `st.expander` cards showing score badge, classification, and full profile text.

**Tab 3 — Compare & Temporal:** Two `st.selectbox` dropdowns; both required before any content renders. Side-by-side score metrics + profiles. Temporal section: reviews split into weekend/night vs. weekday/day buckets by keyword matching (`split_temporal()`); top 3 excerpts shown per bucket. Placeholder expander for production time-series charts.

**Tab 4 — Chat with MiaNoise:** `st.form` with text input + Send button pinned at top of tab (always visible). Messages render below in reverse-chronological order. `agent_history` (LangChain message objects) stored in `st.session_state` for multi-turn context; display messages (`{role, content}` dicts) stored separately for `st.chat_message` rendering.

**Connects to:** `ingestion/db.py`, `ui/map_builder.py`, `agent/executor.py`, `streamlit_folium`, `shapely`.

---

## Modules Stubbed — Not Yet Implemented

| Path | Sprint | Purpose |
|---|---|---|
| `eval/` | 4 | RAGAS evaluation framework |
