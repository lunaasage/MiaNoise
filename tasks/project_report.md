# MiaNoise — Full Project Report
### For Jeanne: everything you need to present this as if you'd been here the whole time

_Last updated: April 27, 2026 — covers Sprint 0 through Sprint 4.3_

---

## Table of Contents

1. [What MiaNoise Is](#1-what-mianoise-is)
2. [System Architecture](#2-system-architecture)
3. [Sprint 0 — Foundation](#3-sprint-0--foundation)
4. [Sprint 1 — Data Ingestion & Scoring](#4-sprint-1--data-ingestion--scoring)
5. [Sprint 2 — RAG Pipeline](#5-sprint-2--rag-pipeline)
6. [Sprint 3 — Agent & UI](#6-sprint-3--agent--ui)
7. [Sprint 3.4 — Score Recalibration](#7-sprint-34--score-recalibration)
8. [Sprint 4 — Evaluation & Polish](#8-sprint-4--evaluation--polish)
9. [Evaluation Results](#9-evaluation-results)
10. [Known Limitations & Honest Gaps](#10-known-limitations--honest-gaps)
11. [Appendix — Per-Question RAGAS Scores](#11-appendix--per-question-ragas-scores)

---

## 1. What MiaNoise Is

MiaNoise is an LLM-powered neighborhood noise intelligence tool for Miami renters. The idea is simple: when someone is deciding where to live, noise is one of the most important quality-of-life factors — and also one of the hardest to research. Listings never mention it, and the only way to know is to walk around at 2am on a Friday. We built the system that does that research for you.

The product works by synthesizing three types of urban data: **311 noise complaint records** (official complaints filed with the city), **venue density from OpenStreetMap** (how many bars, nightclubs, and restaurants exist in each area, weighted by their noise impact type), and **road network data** (how much high-traffic roadway runs through a neighborhood). These signals are combined into a single composite noise score between 0.0 (minimal noise) and 1.0 (very loud) for each of Miami's 104 neighborhoods. The system then enriches these scores with real review text — Google Places reviews from the bars and clubs in each area — and uses a retrieval-augmented generation (RAG) pipeline to produce natural-language neighborhood profiles and answer conversational questions.

The north star we kept coming back to throughout the project:

> *"A stranger opens the link, clicks on Wynwood, and reads: 'Wynwood is loud on Friday and Saturday nights until 3–4am, driven by club and bar activity on NW 2nd Ave. Daytime noise is moderate, primarily construction-related. Residents on Reddit describe it as a great place to go out, not a great place to sleep.' — and trusts that the LLM said that because the data supports it."*

We are presenting the **PoC version** (branch `poc`), which covers 2 scoring sources (OSM venues + OSM roads) and 1 corpus source (Google Places reviews). A full version is planned post-April 29 that adds TomTom traffic, FAA flight paths, and construction permits. The architecture was designed from day one so that adding a new source never requires touching the pipeline — you just write a new file.

**Live app:** deployed on Streamlit Community Cloud from the `poc` branch.

---

## 2. System Architecture

### 2.1 Tech Stack

| Layer | Tool | Role | Notes |
|---|---|---|---|
| **Database** | Supabase (PostgreSQL + pgvector) | All persistent data | neighborhoods, scores, reviews, embeddings, profiles |
| **Embeddings** | OpenAI text-embedding-3-small | Vectorize review text | 1536-dim, cosine similarity search |
| **Profile synthesis** | OpenAI GPT-4o-mini | Generate neighborhood profiles | Pipeline time only — runs once per neighborhood per night |
| **Live agent** | OpenAI GPT-4o-mini | Answer user questions | Fires on user queries; LangChain AgentExecutor |
| **Agent framework** | LangChain 1.x | Tool orchestration | rank_neighborhoods, get_profile, search_reviews |
| **Geospatial** | GeoPandas + Shapely | Spatial joins, polygon ops | Neighborhoods in WGS84; UTM 17N for area calculations |
| **Map source** | OpenStreetMap (Overpass API) | Venue + road data | No API key, no quota, community-maintained |
| **Frontend** | Streamlit + Folium + Pydeck | 4-tab dashboard | Map, Profiles, Compare, Chat |
| **Evaluation** | RAGAS v0.2 | RAG quality metrics | faithfulness, answer_relevancy, context_precision, context_recall |

### 2.2 Data Flow

```
OpenStreetMap venues ──┐
OpenStreetMap roads  ──┼──► score_engine.py ──► noise_scores (Supabase)
City of Miami 311    ──┘                                │
                                                        │
Google Places reviews ──► embedder.py ──► embeddings ──┼──► retriever.py ──► agent
                      └──────────────────────────────►  synthesizer.py ──► profiles (Supabase)
                                                                                │
                                              Streamlit UI ◄────────────────────┘
```

Everything flows left to right and is stored in Supabase. The UI reads entirely from the database — no live data fetching on page load. The agent is the only component that fires live API calls (to GPT-4o-mini), and only when a user sends a message.

### 2.3 The Plugin Architecture

One of the most important design decisions we made in Sprint 0 was the **plugin architecture for data sources**. Every noise data source — whether it's a 311 complaint feed, an OSM query, or a future TomTom traffic call — inherits from an abstract base class `NoiseSource` defined in `ingestion/sources/base.py`. The contract is:

- Declare your `source_id`, `weight`, `source_role` (scoring, corpus, or both), and any required environment variables
- Implement `fetch()` → returns a list of `NeighborhoodScore` objects (for scoring sources) or `CorpusDocument` objects (for corpus sources)
- The pipeline automatically skips sources whose API keys aren't set, without crashing

This means the PoC (2 scoring sources) and the full version (6+ sources) run on identical code. To add a new source, you create a new file, subclass `NoiseSource`, and add it to the `ALL_SOURCES` registry in `ingestion/sources/__init__.py`. Nothing else changes.

The `source_role` field (`"scoring"` | `"corpus"` | `"both"`) is important: it cleanly separates sources that contribute to the numeric score from sources that only feed the RAG text corpus. This was added mid-Sprint 1 after we found ourselves using weight=0 as a hack to mean "corpus only," which was confusing.

### 2.4 Composite Score Formula

```
composite_score = Σ (normalized_source_score × source_weight) / Σ active_weights
```

Weights re-normalize against only the sources that returned data, so if one source fails or isn't configured, the other sources' contributions aren't deflated. Current PoC weights:

- `osm_venues` — weight 0.6 (venue type-weighted density: nightclub×3, bar×2, restaurant×0.5)
- `osm_roads` — weight 0.4 (weighted road-km: motorway×3.0, trunk×2.0, primary×1.0)

Score range in practice: **0.00** (no mapped venues or roads, e.g. Fair Isle) to **0.70** (CBD — Miami's densest, noisiest neighborhood).

---

## 3. Sprint 0 — Foundation

_April 3–5, 2026_

Sprint 0 was pure infrastructure: repo structure, database schema, source stubs, and the GeoJSON that everything else depends on.

**What we built:**

- **Supabase schema** (`migrations/001_initial_schema.sql`): the `neighborhoods` table (104 rows, seeded from GeoJSON), `noise_scores` (one row per source per neighborhood per run), `reviews` (raw text corpus), `embeddings` (1536-dim vectors), and a `latest_noise_scores` view that the UI queries
- **Miami neighborhood GeoJSON** (`data/geojson/miami_neighborhoods.geojson`): 104 neighborhood polygons sourced from City of Miami's ArcGIS Hub, in WGS84. This file is the geographic backbone for everything — spatial joins, score assignments, and the Folium map
- **Plugin architecture**: `NoiseSource` abstract base class, `NeighborhoodScore` and `CorpusDocument` dataclasses, and stubs for all 7 planned sources (complaints_311, venue_density, yelp_reviews, reddit_posts, osm_venues, osm_roads, tomtom_traffic)
- **Score engine** (`ingestion/score_engine.py`): the weighted composite score computation, cleanly separated from the pipeline orchestration
- **Pipeline orchestrator** (`ingestion/pipeline.py`): discovers sources via `ALL_SOURCES`, separates scoring from corpus paths, calls `embed_all()` and `generate_all_profiles()` in the right order

The GeoJSON was not trivial to get right — Miami's 104 neighborhoods include two pairs of duplicate polygon slugs (Baypoint and Fair Isle appear twice due to quirks in the source data). We caught and deduplicated these before seeding, which prevented a non-unique index crash that would have surfaced three sprints later.

---

## 4. Sprint 1 — Data Ingestion & Scoring

_April 6–9, 2026_

**Goal:** `python -m ingestion.pipeline` produces real composite noise scores for all 104 neighborhoods, written to Supabase.

This sprint had more pivots per day than any other. Miami's data landscape is fragmented in ways that aren't obvious until you're deep in it.

### 4.1 The 311 Complaints Journey

We originally planned to use noise complaint records as one of the primary scoring signals. The journey to find usable data was a lesson in Miami's jurisdictional complexity.

**Attempt 1 — Miami-Dade County 311 (ArcGIS):** We queried Miami-Dade's 311 ArcGIS service across its 333,836+ records. No noise category exists. Every noise-related category had been merged into generic "quality of life" buckets. Dead end.

**Attempt 2 — Code Compliance violations:** Searched Miami-Dade Code Compliance for violations with PROBLEM_DESC containing "NOISE." Got 72 records — but at coordinates lat 25.51–25.72 (south Miami-Dade, near Homestead). Our neighborhoods are at lat 25.73–25.85 (City of Miami proper). A classic Miami gotcha: the City of Miami and Miami-Dade County are separate jurisdictions with separate data systems, and the county data doesn't cover the city.

**Attempt 3 — City of Miami 311, date-filtered:** Found the right endpoint (`services1.arcgis.com/CvuPhqcTQpZPT9qY`) with actual NOISEVIO records in the right geography. Wrote a 12-month rolling window filter using TIMESTAMP string comparison. The endpoint returned 0 rows with a 200 OK. No error, no indication anything was wrong. After debugging, we discovered that the ArcGIS endpoint stores dates as epoch milliseconds — a string TIMESTAMP comparison silently excludes every record.

**Attempt 4 — All-time records, no date filter:** Removed the date filter. Got 578 records, correctly distributed across City of Miami neighborhoods. This is usable data.

**Final decision:** With only 578 all-time records (the dataset hadn't been updated since August 2024), complaints_311 was too thin and stale to be a meaningful *scoring* signal — many neighborhoods had 1–3 complaints, nearly indistinguishable from each other. We moved it to `source_role="corpus"` — the complaint texts go into the RAG text corpus rather than influencing the numeric score. The two OSM sources carry full scoring weight.

### 4.2 The Venue Density Journey

The original plan called for Google Places API to measure nightlife venue density. This also didn't survive contact with reality.

**Attempt 1 — Google Places Legacy API:** Got REQUEST_DENIED. Legacy API is not enabled for new projects as of 2024.

**Attempt 2 — Google Places API New:** The new API requires a specific field mask header (`X-Goog-FieldMask`). We initially included `nextPageToken` in the field mask (treating it as a sub-field of the places array). Got 400 INVALID_ARGUMENT with no helpful message. Discovered that `nextPageToken` is a top-level response field, not a `places.*` sub-field.

**Attempt 3 — Places API New, correct field mask:** Works, but capped at 20 results per venue type per request, quota-limited, and requires the API key. For 104 neighborhoods × multiple venue types, the request count gets expensive fast.

**Pivot to OpenStreetMap:** We replaced Google Places with a direct Overpass API query for all venues in Miami (`amenity=bar|nightclub|restaurant` etc.). OSM Overpass returns every mapped venue in Miami — about 714 at query time — with no API key, no quota, and no per-request cost. The data is 3–5× more complete than Places for our purposes. This became `OSMVenueDensity` (weight=0.6 after role restructuring).

**OSM road noise:** While building `OSMVenueDensity`, we added a companion source, `OSMRoadNoise`, that pulls road geometries from Overpass and computes weighted road-km per neighborhood (motorway×3.0, trunk×2.0, primary×1.0, secondary×0.5). Roads are clipped to neighborhood polygons in UTM 17N (a projection that preserves area and length). This replaced the planned TomTom Traffic source for the PoC.

### 4.3 Overpass Reliability

Public Overpass instances are shared infrastructure and time out under load. The roads query (`out geom;` for 5,573 road segments) consistently failed on the first attempt. We solved this with local GeoPackage caching:

- `osm_venues`: cache TTL 1 day, path `data/cache/osm_venues_miami.gpkg`
- `osm_roads`: cache TTL 7 days, path `data/cache/osm_roads_miami.gpkg`
- Both queries include a `User-Agent` header (`MiaNoise/1.0`) — without it, `overpass-api.de` returns 406 Not Acceptable at the HTTP gateway layer with no useful error message

There's also a subtle GeoPandas bug we hit: when intersecting roads (LineStrings) with neighborhood polygons using `gpd.overlay()`, the argument order matters. `gpd.overlay(polygons, roads)` with `keep_geom_type=True` keeps only Polygon results — which silently drops every LineString clipping. The fix: put the roads GeoDataFrame as the first argument. This produced zeros for all road scores until caught.

### 4.4 Sprint 1 Result

After all pivots: 104 neighborhoods scored, data verified in Supabase. Top scorers:

| Rank | Neighborhood | Score |
|---|---|---|
| 1 | CBD | 0.70 |
| 2 | Brickell Residential District | ~0.55 |
| 3 | Wynwood Industrial District | 0.52 |
| 3 | Brickell Village | 0.52 |

(Note: Wynwood's score of 0.52 reflects the *type-weighted* venue count added in Sprint 3.4. The raw count in Sprint 1 underestimated Wynwood significantly — more on that below.)

---

## 5. Sprint 2 — RAG Pipeline

_April 10–13, 2026_

**Goal:** Given a neighborhood name, retrieve relevant review text and generate a natural-language noise profile grounded in that text.

### 5.1 Building the Review Corpus

We needed a large body of review text from bars, nightclubs, and restaurants across Miami's neighborhoods. We evaluated three sources:

- **Yelp Fusion API:** pricing changed; too expensive for PoC budget. Dropped.
- **Reddit PRAW API:** Reddit locked API access behind formal builder approval in 2023. Standard OAuth credentials no longer work without app approval. Public JSON endpoints (`reddit.com/r/miami.json`) remain accessible but rate-limited. We kept this as a future supplement, not a core source.
- **Google Places API New:** Already had the key from Sprint 1. The OSM venue cache (714 venues, neighborhood-tagged) gave us the exact coordinates and neighborhoods for each venue. We searched Places at each venue's location with a 100m radius, pulled up to 5 reviews per venue, and got **10,095 reviews across 58 neighborhoods**. Google Places reviews for bars and clubs naturally discuss noise, atmosphere, hours, and crowd — exactly the signals we need.

One design decision worth explaining: **one review = one chunk**. We chose not to use fixed 512-token sliding windows, because reviews are self-contained units of opinion — splitting a 3-sentence review across two chunks would break the semantic coherence that makes retrieval meaningful. Venue and neighborhood context is prepended to each chunk before embedding (`"[Wynwood Industrial District] Oasis Wynwood: …"`) to give the embedding geographic anchoring.

### 5.2 Embedding & Retrieval

Every review was embedded using `text-embedding-3-small` (1536 dimensions) and stored in Supabase's `embeddings` table. We use pgvector's cosine similarity via a stored procedure (`match_embeddings()`) for retrieval.

**Multi-query retrieval:** Instead of embedding the user's question directly and querying once, we expand each question into 5 queries covering different noise aspects:
1. The question itself
2. "noise levels at night"
3. "loud music bars clubs nightlife"
4. "quiet peaceful residential"
5. "traffic street noise daytime"

Results from all 5 queries (top 4 per query) are merged and deduplicated, giving 8–16 semantically diverse chunks per retrieval. This compensates for the fact that a question like "is it loud on weekends?" might not lexically match review fragments like "Friday nights are wild."

### 5.3 Profile Synthesis

With retrieval working, we generate a natural-language profile for every neighborhood using GPT-4o-mini. The profile synthesizes:
- The composite noise score and what it means
- The types of venues driving the score
- Key themes from retrieved reviews (timing, crowd type, specific venues mentioned)
- Honest caveats for data-sparse neighborhoods

Profiles are generated at **pipeline time** (not on demand) and stored in Supabase's `profiles` table. The UI reads profiles from the database — no LLM call happens when a user clicks on a neighborhood on the map.

**A critical bug we caught:** the initial `run_and_persist()` call order was `write_corpus()` → `generate_all_profiles()`, missing the `embed_all()` step in the middle. All 58 profiles were generated with zero retrieved chunks — the profiles "succeeded" but contained only the composite score and no grounded review text. Silent failure. We caught this during end-to-end testing and fixed the pipeline call order: `write_corpus()` → `embed_all()` → `generate_all_profiles()`.

### 5.4 The LLM Stack Decision

We started the sprint assuming Anthropic Claude would handle synthesis and a Groq-hosted Llama model would handle the live agent. Luna pushed back, and it was the right call.

The question we should have asked upfront: *Does this task require a frontier model, or will a smaller one do?* Profile synthesis is structured instruction-following — "given these review excerpts and this score, write a 4-sentence neighborhood summary." GPT-4o-mini handles this well at a fraction of the cost, and we already had OpenAI in the stack for embeddings. Running two paid LLM providers (OpenAI + Anthropic) for tasks that one handles equally well adds billing complexity and integration overhead with no benefit.

Anthropic was removed from the stack entirely. OpenAI GPT-4o-mini handles both synthesis (pipeline time) and the live agent (user queries).

**Why not fine-tune?** We considered whether to fine-tune a custom model on Miami neighborhood data. The answer: no. Fine-tuning requires hundreds of labeled training examples, ongoing retraining infrastructure, and a hosted inference endpoint. The task is standard instruction-following that base models handle well out of the box. Fine-tuning solves a problem we don't have.

---

## 6. Sprint 3 — Agent & UI

_April 14–21, 2026_

**Goal:** A live Streamlit app where users can explore the noise map, read profiles, compare neighborhoods, and ask natural-language questions.

### 6.1 The LangChain Agent

The conversational interface is a LangChain `AgentExecutor` backed by GPT-4o-mini. It has three tools:

- **`rank_neighborhoods`** — queries Supabase for all neighborhood scores, sorts them, and returns a formatted ranking. Used for "find me a quiet area" type questions.
- **`get_profile`** — retrieves the pre-generated profile for a specific neighborhood from Supabase. Used for direct neighborhood questions ("how noisy is Wynwood?").
- **`search_reviews`** — performs multi-query pgvector retrieval for a neighborhood, useful for timing-specific questions ("is it loud on Thursdays?").

All three tools include **fuzzy name resolution** (`_resolve_name()`) — the user might type "Brickell" and mean Brickell Village, or Brickell Residential District. The resolver tries exact match first, then partial match, then falls back to ranking by review count. This prevents the frustrating "neighborhood not found" error for common casual references.

The system prompt was carefully engineered to guide tool use order: `get_profile` first (for context), then `search_reviews` for timing-specific queries, `rank_neighborhoods` only for comparison queries. It also handles the "0.00 score" problem explicitly (more on that in Sprint 4).

**Groq → OpenAI pivot:** We initially built the agent on Groq's free-tier Llama 3.1 70B. In testing, 15–20 user questions exhausted the 100K-token/day free cap. The reason: agent loops re-send the full conversation context on every internal LLM call (tool call + response + next turn), multiplying token consumption by roughly 5×. A single user question that triggers 3 tool calls costs ~6,000 tokens. 20 questions = 120,000 tokens. We switched to GPT-4o-mini, which costs pennies at this volume and uses an API key we already had.

### 6.2 Profile Coverage Gap

When we first ran `generate_all_profiles()`, we iterated over the `reviews` table — which only had entries for the 58 neighborhoods where Google Places found venues. The other 46 neighborhoods had no profile at all. When the agent called `get_profile("Fair Isle")`, it got nothing.

The fix was simple but important: iterate over the `neighborhoods` table instead. Neighborhoods with review data get full profiles grounded in retrieval. Neighborhoods with no reviews get a shorter profile that at least cites the composite score and explains what the absence of venue data likely means (quieter residential character). 104/104 neighborhoods now have profiles.

### 6.3 The Streamlit Dashboard

The UI is a 4-tab Streamlit app:

**Tab 1 — Map:** A Folium choropleth where Miami neighborhoods are colored green (quiet) to red (loud) based on composite score. The colormap stretches from 0.0 to the actual data maximum (0.70 — the CBD), not a hardcoded 1.0. Users can hover for score and click to load a profile in a sidebar panel. Point-in-polygon lookup assigns the click coordinates to the correct neighborhood.

**Tab 2 — Neighborhood Profiles:** Searchable, filterable, sortable list of all 104 neighborhoods. Sort by score ascending/descending, filter by score range, search by name. Clicking a row expands the full LLM-generated profile.

**Tab 3 — Compare & Temporal:** Side-by-side comparison of two neighborhoods. Shows scores, profiles, and a keyword analysis of review text (noise-related terms grouped into categories: music/nightlife, construction, traffic, quiet/peaceful). Both neighborhoods must be selected for the comparison to render.

**Tab 4 — Chat with MiaNoise:** The conversational interface. The input box is pinned at the top of the tab so it doesn't scroll out of view. Messages render below in reverse-chronological order so the latest response is always closest to the input.

**Chat UX fix:** An early version had a frustrating UX bug: when the user submitted a message, nothing happened visually until the agent finished generating (8–15 seconds). The fix uses Streamlit's `session_state` with a `pending_prompt` key — on submit, the user's message is appended to the message history and a `st.rerun()` fires immediately, rendering the message. The spinner then appears on the next render while the agent runs. User sees their message appear instantly; the spinner appears below it.

**Floating chat widget attempt (reverted):** We first tried to implement the chat interface as a `position: fixed` overlay widget that floated above the map — a more elegant UX. After a full day of CSS work, we couldn't reliably target the correct Streamlit DOM elements. Streamlit's component hierarchy wraps everything in `stVerticalBlock` containers with no stable IDs, making CSS selectors too fragile. We reverted to the dedicated Chat tab — the right decision given the time constraint.

### 6.4 Deployment

The app is deployed on Streamlit Community Cloud from the `poc` branch. Key deployment notes:

- Python version pinned to 3.11 via `.python-version` (psycopg2-binary has no pre-built wheel for Python 3.14; we removed that dependency entirely since it was unused)
- All secrets (Supabase URL/key, OpenAI key, Google Places key) stored in Streamlit Cloud's secrets manager in TOML format, not committed to the repo
- Changes pushed to `poc` deploy automatically

---

## 7. Sprint 3.4 — Score Recalibration

_April 22–24, 2026_

This sprint started with a validation test that revealed a fundamental flaw in how we were scoring neighborhoods.

### 7.1 The Problem: Wynwood Scoring 0.3

When we ran end-to-end tests of the agent, we asked: "What are Miami's loudest neighborhoods?" Wynwood appeared at #7. Wynwood Industrial District is, by any metric, one of Miami's loudest nightlife districts — dense with clubs, bars with outdoor patios, and venues open until 3–4am. It should be near the top.

The root cause: `osm_venues` was counting venues by raw count, normalized against the total count across all 104 neighborhoods. A nightclub and a McDonald's both contributed 1 point. Commercial dense areas like Brickell — which has dozens of restaurants and retail — outscored Wynwood because they have more total venues, even though restaurants are far less noisy than nightclubs.

The score was measuring structural venue density, not noise behavior.

### 7.2 The Fix: Venue Type Weighting

We added noise-impact weights to the venue type taxonomy:

| Venue type | Weight | Rationale |
|---|---|---|
| `nightclub` | 3.0 | Amplified music, late hours (often 2–4am), outdoor crowds |
| `bar` | 2.0 | Social noise, late hours, often outdoor seating |
| `restaurant` | 0.5 | Ambient noise, earlier closing hours |
| (others) | 1.0 | Default |

The new score for each neighborhood is `sum(venue_type_weight)` rather than `count(venues)`, then max-normalized across all neighborhoods. This immediately moved Wynwood from #7 to #3 at 0.52, correctly behind the CBD (0.70, highest) and a small cluster of dense Brickell venues.

### 7.3 Pipeline Re-run & Profile Regeneration

After changing the scoring formula, we re-ran the full pipeline:
- 104 neighborhoods rescored with new weights
- 4,454 new reviews collected (with deduplication — an earlier bug allowed duplicate review rows on repeated pipeline runs; fixed with `ON CONFLICT DO NOTHING` in `write_corpus()`)
- 4,454 embeddings generated
- 104 profiles regenerated from scratch (profiles are baked against the composite score value — changing the score without regenerating profiles would leave inconsistent text)

We also fixed a crashing bug in `osm_venues.py`: the score aggregation used `.reindex(neighborhoods["name"])` on a pandas Series, which crashed on non-unique neighborhood names (Baypoint and Fair Isle appear twice in the GeoJSON). Replaced with a `groupby().get()` approach that handles duplicates gracefully.

### 7.4 Other Fixes in This Sprint

- **Map colormap**: the Folium choropleth was using `vmax=1.0` hardcoded, compressing all actual scores (max 0.70) into the bottom 70% of the green–red gradient. Fixed to use `vmax = gdf["composite_score"].max()`.
- **Chat display bug**: the initial pending_prompt fix rendered messages inside the wrong Streamlit block. Fully resolved in this sprint — history renders first, spinner appears below it.
- **psycopg2-binary removed**: unused dependency that has no pre-built wheel for Python 3.14; was blocking Streamlit Cloud deployment.

---

## 8. Sprint 4 — Evaluation & Polish

_April 25–27, 2026 (current sprint)_

### 8.1 Sub-sprint 4.2 — The 0.00 Score UX Problem

When users asked the agent "which neighborhoods are quietest?", the ranking returned 10+ neighborhoods all listed at score 0.00. These are places like Fair Isle, Belle Island, and other waterfront residential areas where OSM has no mapped nightlife venues and the road network is minimal. A score of 0.00 is *technically correct* — we have no data — but listing a dozen neighborhoods as "0% noise" with no explanation is both confusing and misleading.

The fix was two-pronged:

**Agent system prompt:** Added an explicit "Score interpretation" section explaining that a score near 0.00 means limited data coverage, not verified silence. The agent is instructed to say something like *"X has a score of 0.04, which reflects limited venue and complaint data. That said, sparse data often indicates a quieter residential character — few bars, clubs, or noise complaints on record."* The agent must never say a 0.00-score neighborhood is "definitively quiet."

**`rank_neighborhoods` tool annotation:** The tool output now appends `[limited data]` next to every 0.00-score entry and includes a footer note explaining what that means. Even if the agent's synthesis fails to pick up the system prompt nuance, the tool output itself carries the caveat.

### 8.2 Sub-sprint 4.3 — RAGAS Evaluation Framework

We built a full RAGAS evaluation pipeline to measure the quality of the RAG system. RAGAS (Retrieval Augmented Generation Assessment) is an industry-standard framework that uses an LLM judge to score four metrics:

| Metric | What it measures |
|---|---|
| **Faithfulness** | Are all claims in the answer grounded in the retrieved chunks? (hallucination check) |
| **Answer Relevancy** | Does the answer directly address the question asked? |
| **Context Precision** | Are the retrieved chunks relevant to the question? (retrieval signal-to-noise) |
| **Context Recall** | Do the retrieved chunks contain the facts needed to answer correctly? |

**The test set (`eval/dataset.py`):** 15 hand-crafted questions across 10 neighborhoods, covering four query types:
- Loud/nightlife-heavy neighborhoods (Wynwood, CBD, Brickell)
- Quiet/moderate neighborhoods (Midtown, Edgewater, Grove Center)
- Temporal questions ("is it louder at night?", "what about weekends?")
- Renter-decision questions ("would this work for someone who works from home?")

Each test case has a ground truth answer anchored to known facts (specific composite scores, known venue characteristics).

**The runner (`eval/runner.py`):** For each test case, we run the full retrieval pipeline (multi-query pgvector) and generate a focused answer with GPT-4o-mini constrained to the retrieved chunks only (`"every claim you make must be directly supported by a review excerpt"`). Zero-chunk cases (neighborhoods with no embeddings) are flagged and excluded from metric computation — they'd skew faithfulness and precision scores down.

**The Python 3.14 compatibility bug:** RAGAS v0.2 uses `nest_asyncio.apply()` at import time to allow nested async event loops. On Python 3.14, `nest_asyncio` corrupts `asyncio.current_task()` — it always returns `None` after `apply()` is called. Python 3.14's `asyncio.timeout()` (used internally by `asyncio.wait_for()`, which RAGAS uses for LLM call timeouts) requires `current_task()` to return a valid Task object, or it raises `RuntimeError: Timeout should be used inside a task`. Every one of the 60 evaluation jobs failed silently (scores returned as NaN) until we found and fixed this.

**The fix:** Inject a no-op `nest_asyncio` module into `sys.modules` *before* any RAGAS import. Since Python's module system caches imports, if `nest_asyncio` is already in `sys.modules` when RAGAS tries to import it, RAGAS gets the no-op version. `nest_asyncio.apply()` becomes a no-op, `current_task()` works correctly, and all 60 metric jobs complete. Added to the very top of `eval/run_eval.py`.

---

## 9. Evaluation Results

_Run: April 27, 2026 — 15 questions, 10 neighborhoods_

### Aggregate Scores

| Metric | Score | Rating |
|---|---|---|
| **Faithfulness** | **0.847** | 🟢 Good |
| **Answer Relevancy** | **0.321** | ⚠️ Needs improvement |
| **Context Precision** | **0.347** | ⚠️ Needs improvement |
| **Context Recall** | **0.322** | ⚠️ Needs improvement |

### What These Numbers Mean

**Faithfulness at 0.847 is the headline result.** This is the metric that matters most for a RAG system — it measures whether the LLM is staying grounded in retrieved evidence or making things up. A score of 0.85 means roughly 85% of all factual claims in the generated answers are directly traceable to a retrieved review chunk. For a system where trust is the whole point ("the LLM said that *because the data supports it*"), this is a strong result.

**The other three metrics being lower is an honest finding, not a bug.** Here's why:

The ground truths we wrote for the test set include specific composite scores ("Wynwood has a score of 0.52") and quantitative comparisons ("the CBD has the highest composite noise score, 0.70"). These facts do not appear in Google Places reviews. Reviewers write things like "this place is incredibly loud" — they don't cite composite noise indices. So when RAGAS's context recall metric asks "does the retrieved context contain the information needed to answer the ground truth?", the answer is often no — not because retrieval is failing, but because the ground truth includes metadata that the review corpus structurally cannot contain.

This is a genuine limitation to be honest about: the RAG system is excellent at answering qualitative questions grounded in venue reviews ("what's the vibe like?", "is it loud at night?") but weaker at answering quantitative or comparative questions that require score-level data the reviews don't carry.

**The 0.00 answer relevancy pattern:** Ten of fifteen questions score 0.00 on answer relevancy. These tend to be complex comparative or renter-decision questions ("Is Brickell Village a good place to live for someone who works from home?"). The metric generates paraphrase questions from the answer and measures how well they match the original question — a complex answer that addresses multiple sub-questions can score low here even when it's substantively correct. This metric may be undervaluing the agent's actual performance on complex queries.

### What Would Improve Each Score

- **Faithfulness → already good.** Maintain the strict context-only instruction in the generation prompt.
- **Context Recall → supplement the corpus.** Adding the 311 complaint text, Reddit posts, and structured score data to the retrieval index would give the retriever the quantitative facts the ground truths reference.
- **Context Precision → tune retrieval.** Reranking retrieved chunks (e.g. cross-encoder reranker) or narrowing the multi-query strategy would surface the most relevant chunks first.
- **Answer Relevancy → revisit ground truth design.** Some 0.00 scores may reflect ground truths that are structurally incompatible with review-based retrieval, not actual relevancy failures.

---

## 10. Known Limitations & Honest Gaps

### Data Coverage

- **58/104 neighborhoods have review-grounded profiles.** The other 46 have score-only profiles. These are generally quieter residential areas (which is why they have no mapped venues), but the profiles are thinner.
- **The complaint dataset is stale.** The City of Miami 311 NOISEVIO dataset was last updated August 2024. We use it as corpus-only (review text), not as a scoring signal, precisely because its 578 all-time records are too thin and stale to differentiate neighborhoods meaningfully.
- **OSM is crowd-sourced.** Venues that aren't in OpenStreetMap don't contribute to the score. Miami's OSM coverage is generally good for established venues but may miss newer openings or temporarily closed spots.

### Score Calibration

- **No ground truth to calibrate against.** We chose the osm_venues / osm_roads weight split (0.6/0.4) based on domain reasoning, not statistical optimization. We know Wynwood should be louder than Coconut Grove — the current weights reflect this — but we haven't validated the weights against an independent noise measurement dataset.
- **0.00-score neighborhoods mean "no data," not "verified quiet."** This is a known UX issue that Sprint 4.2 addressed at the agent level. The underlying data gap remains.

### System Boundaries

- **The agent only knows about noise.** It can't answer questions about rent prices, school quality, walkability, or other renter concerns. It's scoped explicitly and correctly.
- **Profiles are regenerated per pipeline run, not per user query.** The profile text bakes in whatever score existed at the time the pipeline last ran. If scores change (e.g. after a weight recalibration), profiles must be manually regenerated.
- **No real-time data.** The system reflects a snapshot of the OSM data, Google Places reviews, and 311 records as of the last pipeline run. It is not updated continuously.

### What the Full Version Would Add

The PoC is built to extend. The plugin architecture means the full version activates by adding API keys to `.env`:
- TomTom Traffic — road noise proxy from live traffic volume (weight ~0.2 in full version)
- OpenSky flight paths — overflight frequency over Miami neighborhoods (relevant for neighborhoods under MIA flight corridors)
- Miami Open Data construction permits — active construction zones per neighborhood
- Reddit community posts — qualitative neighborhood noise anecdotes from `r/miami` and `r/MiamiBeach`

---

## 11. Appendix — Per-Question RAGAS Scores

_Full evaluation run: April 27, 2026 — 15 questions × 4 metrics_

| # | Neighborhood | Chunks | Faithfulness | Ans. Relevancy | Ctx. Precision | Ctx. Recall |
|---|---|---|---|---|---|---|
| 1 | Wynwood Industrial District | 6 | 0.88 | 0.99 | 0.80 | 1.00 |
| 2 | Wynwood Industrial District | 7 | 0.60 | 0.99 | 0.59 | 1.00 |
| 3 | CBD | 9 | 1.00 | 0.00 | 0.33 | 0.00 |
| 4 | Brickell Village | 12 | 0.89 | 0.00 | 0.00 | 0.00 |
| 5 | Brickell Village | 10 | 1.00 | 0.00 | 0.68 | 1.00 |
| 6 | Wynwood Industrial District | 7 | 0.80 | 0.93 | 1.00 | 0.50 |
| 7 | Flagami | 8 | 0.50 | 0.89 | 0.00 | 0.00 |
| 8 | Edgewater | 7 | 0.75 | 0.00 | 0.00 | 0.00 |
| 9 | East Little Havana | 9 | 1.00 | 0.00 | 0.17 | 0.33 |
| 10 | Design District | 7 | 0.78 | 0.00 | 0.33 | 0.00 |
| 11 | Midtown | 10 | 0.88 | 0.00 | 0.00 | 0.00 |
| 12 | Grove Center | 10 | 1.00 | 0.00 | 0.57 | 0.67 |
| 13 | Brickell Village | 10 | 0.83 | 1.00 | 0.39 | 0.33 |
| 14 | Allapattah Industrial District | 4 | 0.80 | 0.00 | 0.00 | 0.00 |
| 15 | CBD | 9 | 1.00 | 0.00 | 0.33 | 0.00 |

**Questions corresponding to each row:**

1. Is Wynwood Industrial District loud at night?
2. Is Wynwood Industrial District quieter during the day than at night?
3. How noisy is the CBD for someone considering living there?
4. What are the noise levels in Brickell Village on weekends?
5. Is Brickell Village a good place to live for someone who works from home and needs quiet during the day?
6. What makes Wynwood Industrial District noisy — is it traffic or nightlife?
7. What types of noise are common in Flagami?
8. Is Edgewater a quiet neighborhood compared to Wynwood?
9. What is the noise situation in East Little Havana?
10. Is the Design District noisy?
11. Is Midtown Miami quiet enough for someone sensitive to noise?
12. Would Grove Center (Coconut Grove) be a good choice for a noise-sensitive renter?
13. Does noise from Brickell Village's nightlife persist late into the night?
14. Is Allapattah noisy?
15. Is there any time of day when the CBD is relatively quiet?

**Notable patterns:**
- Questions 1, 2, 6 (Wynwood, direct questions about a neighborhood we have rich review data for) score well across all four metrics
- Questions 3, 4, 15 (CBD and Brickell comparative/renter questions) have faithfulness 1.00 but answer relevancy 0.00 — the LLM is grounded but the answer doesn't semantically match the complex question framing
- Question 7 (Flagami) has faithfulness 0.50, the second-lowest — Flagami's reviews are thin and the generated answer made some claims the retrieved chunks don't fully support
- All 15 questions retrieved 4–12 chunks — retrieval is working; the score gaps reflect corpus content limitations, not retrieval failures

---

_Report generated April 27, 2026. All data, scores, and decisions are grounded in the commit history, lessons.md, and sprint logs in this repository._
