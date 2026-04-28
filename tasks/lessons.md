# MiaNoise — Lessons Learned

Read this at the start of every session. Update after every correction or unexpected finding.

---

## Sprint 1

### L1 — Verify data availability before writing any fetch logic
**What happened:** Spent multiple iterations on Miami-Dade 311 (no noise category), then Code Compliance violations (wrong geography: lat 25.51–25.72 vs. City of Miami 25.73–25.85), before finding the correct endpoint (City of Miami 311, separate jurisdiction).
**Lesson:** Before writing a single line of fetch code, run a `returnCountOnly` query against the actual endpoint to verify (a) the noise-related category exists, (b) there are records in the target geography, (c) the dataset is being actively updated.
**Rule:** Data Integrity Gate — mandatory before any source implementation.

### L2 — A 200 OK with zero rows is not the same as a working query
**What happened:** The TIMESTAMP date filter on the City of Miami 311 endpoint silently returned 0 rows with a 200 OK. The dataset stores dates as epoch milliseconds; a string TIMESTAMP comparison produces no error and no results.
**Lesson:** After writing any WHERE clause that filters rows: run it with `returnCountOnly` first, then compare against the no-filter count. If zero rows and no error, the filter syntax is wrong — not the data.
**Rule:** Never assume a 200 OK with 0 results means "no data." Verify the filter logic independently.

### L3 — Check dataset freshness before designing a rolling-window strategy
**What happened:** Designed a 12-month rolling window for 311 complaints. The dataset hadn't been updated since August 2024. The window excluded all 578 records.
**Lesson:** Before committing to a recency filter, query `ORDER BY date_field DESC LIMIT 5` to find the most recent record. If the dataset is stale, a rolling window is the wrong design.
**Rule:** Data Integrity Gate — check freshness (max date) before choosing a time window strategy.

### L4 — Miami's jurisdictional fragmentation will bite repeatedly
**What happened:** "Miami" data is split across City of Miami, Miami-Dade County, and Miami Beach — separate jurisdictions, separate APIs, separate data quality. Miami-Dade 311 has no noise data. City of Miami 311 does.
**Lesson:** When a Miami Open Data source returns unexpected results, check jurisdiction first. The City of Miami neighborhoods (lat ~25.73–25.85) are covered by `services1.arcgis.com/CvuPhqcTQpZPT9qY`, not the Miami-Dade county endpoints.
**Rule:** When a data source returns 0 or geographically wrong results for Miami, jurisdiction mismatch is suspect #1.

### L5 — Google Places API New: nextPageToken is not a field mask sub-field
**What happened:** Including `nextPageToken` in `X-Goog-FieldMask` caused a 400 INVALID_ARGUMENT. It's a top-level response field, not a `places.*` sub-field.
**Lesson:** Use `X-Goog-FieldMask: places.id` only. `nextPageToken` is returned automatically in the response body regardless.
**Rule:** When a Places API New call returns 400, check the field mask first.

### L6 — Mark tasks complete only after an end-to-end run, not after writing code
**What happened:** Sprint 1 was "closed" after writing the source implementations. The pipeline hadn't been run. When we actually ran it: complaints_311 returned 0 (date filter bug), both OSM sources timed out (transient Overpass load), venue_density ran a 2-minute fetch for weight=0.
**Lesson:** A source isn't done when `fetch()` is written. It's done when `python -m ingestion.pipeline` produces non-zero, geographically plausible scores logged to Supabase.
**Rule:** Never mark a sprint done without running the full pipeline end-to-end.

### L7 — 578 complaints over 9 years is thin signal for 104 neighborhoods
**What happened:** complaints_311 at weight=0.3 is based on a dataset last updated August 2024 with a max of 45 complaints per neighborhood (CBD). This is thin. Many neighborhoods have 1–3, which scores near zero and is nearly indistinguishable from noise.
**Lesson:** Before assigning a weight to a source, evaluate its effective differentiation power: what's the distribution across neighborhoods? A source where 80% of neighborhoods score 0.0–0.05 contributes almost nothing.
**Open question:** Should complaints_311 weight drop to 0.1, or be used only in the RAG corpus rather than the numeric score?

---

### L8 — gpd.overlay argument order matters for mixed geometry types
**What happened:** Added `keep_geom_type=True` to `gpd.overlay(nbhd_utm, roads_utm)`. With df1=polygons and df2=linestrings, `keep_geom_type=True` keeps only Polygon results — which drops all LineString clippings (the actual road segments). Result: empty clipped GeoDataFrame → all scores zero. Previous runs worked by accident because some road ways form closed loops (roundabouts), producing Polygon intersection results.
**Lesson:** When intersecting polygons with linestrings via `gpd.overlay`, put the linestring GDF as df1. Then `keep_geom_type=True` (default) correctly retains LineString results.
**Fix:** `gpd.overlay(roads_utm, nbhd_utm, how="intersection")` — df1=roads.

### L9 — overpass-api.de returns 406 without a User-Agent header
**What happened:** Overpass primary endpoint returned 406 Not Acceptable on all requests. The 406 disappeared when a `User-Agent` header was added. Without User-Agent, requests are rejected at the HTTP gateway layer, not the query layer — no error message, no indication the query was even parsed.
**Lesson:** Always include `User-Agent` on Overpass requests. Use a descriptive string: `MiaNoise/1.0 (noise intelligence research)`.
**Rule:** All Overpass POST requests must include `OVERPASS_HEADERS`.

### L10 — Heavy Overpass queries need local caching, not just retries
**What happened:** The roads query (`out geom;` for 5573 ways) consistently times out on public Overpass instances under load. Adding more endpoints or retries doesn't solve it — the query is too heavy for shared infrastructure to be reliable. The venues query (`out center;` for 714 points) is lighter and usually succeeds but also times out under load.
**Lesson:** For any Overpass query that fetches geometry (not just centroids), local GeoPackage caching with a TTL is mandatory, not optional. Cache once on first successful fetch; serve from cache thereafter; use stale cache as last resort before returning zeros.
**Rule:** osm_roads TTL=7 days, osm_venues TTL=1 day. Cache path: `data/cache/` (gitignored).

---

## Sprint 2

### L11 — Don't default to paid closed-source LLMs without justification
**What happened:** Defaulted to Anthropic Claude for both profile synthesis and the live agent without questioning whether it was the right tool. Luna challenged this.
**Lesson:** For any LLM choice, ask first: (1) does this need a frontier model or will a smaller open-source one do? (2) does this fire per user or per pipeline run? (3) is there a free tier that covers PoC scale?
**Rule:** Justify every LLM choice. Default to the cheapest viable option; escalate to frontier models only when smaller ones demonstrably fail.

### L12 — Finetuning is not a default solution
**What happened:** Luna asked why we weren't finetuning our own LLM. The honest answer: finetuning requires labeled training data we don't have, adds training/hosting cost, and solves a problem that doesn't exist — the synthesis task is standard instruction-following that base models handle well.
**Lesson:** Finetuning is for when prompting consistently fails at a task, or when you need to bake domain style into weights at scale. For MiaNoise's query space, a well-engineered prompt on a base model is the right tool.
**Rule:** Only consider finetuning if (a) you have 500+ labeled examples and (b) prompt engineering has already failed.

### L13 — Consolidate providers; don't add a new one without reason
**What happened:** Anthropic was in the stack for synthesis while OpenAI was already in the stack for embeddings. No good reason to run two paid LLM providers.
**Lesson:** Each provider = another API key, billing account, SDK dependency, and failure mode. OpenAI GPT-4o-mini handles synthesis as well as Claude Sonnet for this task, at lower cost, with no new integration needed.
**Rule:** Default to the provider already in the stack unless there's a specific capability gap.

---

## Sprint 3

### L14 — Circumradius-based geographic search causes boundary bleed for elongated polygons
**What happened:** `GooglePlacesReviews` computed each neighborhood's circumradius (max distance from centroid to any polygon vertex) and used it as the search radius. Edgewater is a thin waterfront strip — its circumradius is 1205m but its actual width is ~400m. The search circle extended 640m into Wynwood, causing Edgewater profiles to cite Wynwood venues.
**Lesson:** For neighborhood-anchored searches, circumradius is wrong for any non-circular polygon. Use venue-anchored search instead: load pre-mapped OSM venues, spatial-join them to neighborhoods (polygon containment), then search at each venue's exact coordinates with a tight radius (100m). Neighborhood assignment comes from the spatial join, not the search geometry — authoritative regardless of polygon shape.
**Rule:** Never use centroid + circumradius for geographic search boundaries. Use spatial containment to assign neighborhood, not search geometry.

### L15 — Verify full pipeline step order before calling it done
**What happened:** `run_and_persist()` called `write_corpus()` → `generate_all_profiles()` with no `embed_all()` in between. All 58 profiles were generated with 0 review chunks because reviews existed in the reviews table but had no embeddings yet. The profiles silently succeeded — they just contained no grounding.
**Lesson:** Pipeline functions that produce downstream artifacts need explicit, ordered calls. `write_corpus` → `embed_all` → `generate_all_profiles` is a hard dependency chain. Missing the middle step produces silent failure: no error, wrong output.
**Rule:** After adding any pipeline step, trace the full call chain end-to-end and verify each step's output before the next step's input.

### L16 — Groq free tier is incompatible with agent loops at any real usage volume
**What happened:** Groq free tier caps at 100K tokens/day. LangGraph agent loops re-send full conversation context on every internal LLM call — a single user question consumes ~5–7K tokens across multiple hops. 15–20 user questions blow the daily cap. Switching to Groq dev tier was not available at the time.
**Lesson:** Free-tier LLMs work for one-off inference (profile synthesis, a few test calls) but fail immediately for agentic loops, which multiply token consumption by ~5x vs naive estimates. Always estimate token usage accounting for agent loop overhead before committing to a provider.
**Rule:** For any agent loop, assume 5–10× token multiplier vs. single-turn. Size the provider tier accordingly before building. Default to the provider already in the stack (OpenAI was already used for embeddings + synthesis) rather than adding a new one for cost reasons that evaporate at PoC scale.

---

## Sprint 3.4

### L17 — Raw venue count is a poor noise signal; venue type weighting is mandatory
**What happened:** `osm_venues` counted bars, nightclubs, and restaurants equally (1 point each), then max-normalized against all 104 neighborhoods. Wynwood scored 0.3 despite being Miami's loudest nightlife district — it has fewer total venues than dense commercial areas like Downtown, but its mix is specifically nightclubs and bars with outdoor patios open until 3–4am. The score measured structural density, not noise behavior.
**Lesson:** Any venue-count signal needs type weighting before max-normalization. A nightclub generates fundamentally different noise than a restaurant — late hours, amplified music, outdoor crowds. Without weighting, a neighborhood full of cafés outscores a nightlife district.
**Rule:** When adding any venue or amenity count signal, define a noise-impact weight per type before aggregating. Score = sum(type_weight) / max, not raw count / max. Regenerate profiles after any score change — profile text bakes in the composite score value.

---

## Sprint 4

### L18 — RAGAS ground truths must be grounded in the retrieval corpus, not in metadata
**What happened:** The first RAGAS evaluation run (v1 ground truths) produced context_recall of 0.322 and answer_relevancy of 0.321. Investigation showed that 10/15 ground truths referenced specific composite scores ("Wynwood has a score of 0.52", "the CBD scores 0.70"). These facts live in our Supabase metadata layer — they are never present in Google Places reviews. RAGAS context_recall asks: "do the retrieved chunks contain the facts needed to answer the ground truth?" The answer was systematically no — not because retrieval was failing, but because the ground truths tested metadata the corpus structurally cannot contain.
**Lesson:** RAGAS ground truths must be written to match what the retrieval corpus can plausibly contain. For a review-based RAG system, ground truths should reference qualitative, reviewable facts (venue behavior, crowd descriptions, timing observations from reviews) — not numeric scores, rankings, or external metadata. Including metadata in ground truths penalizes the system for a design mismatch, not a retrieval failure. This is a methodology error, not score-gaming to fix.
**Rule:** Before writing ground truths for any RAG evaluation: ask "would this fact plausibly appear in a review from the corpus?" If no → rewrite it in terms of qualitative claims that reviews can support.

### L19 — Faithfulness and answer relevancy are in tension by design in constrained RAG
**What happened:** The generation prompt instructs GPT-4o-mini to ground every claim in retrieved chunks ("every claim you make must be directly supported by a review excerpt"). This maximizes faithfulness (0.847) but causes indirect, hedged answers for questions the corpus doesn't directly cover ("reviews don't specifically address this, but..."). RAGAS answer_relevancy measures whether the answer directly addresses the question — hedged answers score low even when factually correct.
**Lesson:** For a trust-first RAG system, this tradeoff is intentional and correct. Faithfulness is the primary contract with the user. Answer relevancy being lower is an honest signal that the corpus has coverage gaps, not that the system is broken. The right fix is to extend the corpus (more review sources, Reddit posts, structured score documents), not to loosen the generation constraint.
**Rule:** When evaluating a constrained RAG system, lead with faithfulness as the primary metric. Lower answer_relevancy should trigger corpus extension, not prompt relaxation.

---

## Sprint 4 — Streamlit Cloud Deployment

### L20 — Streamlit Cloud uses `runtime.txt` for Python version and `packages.txt` for apt packages
**What happened:** App was failing to deploy — Streamlit Cloud defaulted to Python 3.14 (experimental) despite a `.python-version` file specifying 3.11. `fiona` (geopandas dependency) requires GDAL C libraries not present in the default build image.
**Lesson:** Streamlit Cloud has two separate mechanisms: `runtime.txt` in the repo root for Python version (format: `python-3.12`), and `packages.txt` for apt system packages (one package per line, e.g. `libgdal-dev`, `gdal-bin`). `.python-version` is a pyenv convention not read by Streamlit Cloud.
**Rule:** For any Streamlit Cloud deployment with geospatial dependencies: `packages.txt` must include `libgdal-dev` and `gdal-bin`; `runtime.txt` must pin a stable Python version (3.11 or 3.12).

### L21 — `langchain.agents.create_agent` does not exist; use `langgraph.prebuilt.create_react_agent`
**What happened:** Streamlit Cloud deployment failed at import time with `ImportError: cannot import name 'create_agent' from 'langchain.agents'`. The function used during local development (`create_agent` with `system_prompt=`) was never a public LangChain API — it was a LangGraph internal that happened to be importable locally due to dev install paths.
**Lesson:** The correct public API is `from langgraph.prebuilt import create_react_agent`, using `state_modifier=` instead of `system_prompt=`. Also requires `langgraph` as an explicit `requirements.txt` entry (it's not pulled in transitively by `langchain`).
**Rule:** When using LangGraph agent primitives, always import from `langgraph.prebuilt`, never from `langchain.agents`. Verify imports against the installed package, not just local behavior.

### L22 — `setuptools<82.0.0` required to build geospatial packages from source on Streamlit Cloud
**What happened:** `pandas==2.2.2` failed to build from source on Streamlit Cloud because newer `setuptools` removed `pkg_resources` from the default namespace, which `pandas`'s build backend depends on.
**Lesson:** Pin `setuptools<82.0.0` at the top of `requirements.txt` whenever the dependency set includes packages that build from source (geopandas, pandas, fiona). This is a build-time constraint, not a runtime one.
**Rule:** Any requirements.txt that includes geospatial or numeric packages that may build from source should pin `setuptools<82.0.0` as the first entry.
