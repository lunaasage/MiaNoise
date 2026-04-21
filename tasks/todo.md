# MiaNoise — Task Log

---

## Sprint 1 — Data Ingestion + Score Engine [DONE ✓ confirmed Apr 19]

**Goal:** `python -m ingestion.pipeline` produces real composite noise scores for all neighborhoods, written to Supabase.

### Tasks

- [x] **1.1** `ingestion/db.py` — Supabase I/O layer (seed_neighborhoods, write_scores, load GDF/centroids)
- [x] **1.2** `complaints_311.fetch()` — noise complaints spatial join → scores
- [x] **1.3** Venue density source — nightlife count per neighborhood → scores
- [x] **1.4** `run_and_persist()` + `__main__` entry point in pipeline.py
- [x] **1.5** End-to-end pipeline run with data verified in Supabase

---

### Direction Changes (Audit Trail)

**1.2 — complaints_311 source:**
- Tried: Miami-Dade County 311 ArcGIS endpoints (data_311_YYYY series) → no noise category exists across 333,836+ records. Dead end.
- Tried: Miami-Dade Code Compliance violations (open violations, PROBLEM_DESC LIKE '%NOISE%') → 72 records returned but at lat 25.51–25.72 (south Miami-Dade). Our neighborhoods are at 25.73–25.85. Spatial join: 0 matches for every neighborhood. Geographic mismatch.
- Tried: 12-month rolling window filter using TIMESTAMP string on City of Miami 311 → ArcGIS stores dates as epoch ms; string TIMESTAMP comparison silently returns 0 rows with 200 OK.
- **Decided (with Luna):** City of Miami 311 (separate jurisdiction, `services1.arcgis.com/CvuPhqcTQpZPT9qY`), all-time NOISEVIO records (no date filter — dataset last updated Aug 2024, rolling window excluded everything). 578 records, correct geography.

**1.3 — Venue density source:**
- Tried: Google Places legacy Nearby Search API → REQUEST_DENIED. Legacy API not enabled for new projects.
- Tried: Google Places API New (`POST /v1/places:searchNearby`) with `X-Goog-FieldMask: places.id,nextPageToken` → 400 INVALID_ARGUMENT. nextPageToken is a top-level response field, not a places.* sub-field.
- Tried: Google Places API New with correct field mask → works but capped at 20 results per type per query, requires API key, quota-limited.
- **Decided (with Luna):** Replace Google Places with OSM Overpass (`OSMVenueDensity`, weight=0.5). No API key, no quota, returns every mapped venue in Miami (~3–5× more complete). Google Places deferred to Sprint 2 as optional enrichment (weight=0, disabled via `is_available()=False`).
- **Also added (Luna's suggestion):** `OSMRoadNoise` (weight=0.2) — weighted road-km via Overpass as traffic noise proxy, replacing TomTom for PoC. Motorway×3.0 → primary×1.0. Geometries clipped to neighborhood polygons in UTM 17N.

**Final PoC weight stack:** complaints_311 (0.3) + osm_venues (0.5) + osm_roads (0.2) = 1.0

---

### Direction Change — Source Role Architecture (Sprint 1 cleanup, confirmed Apr 19)

**Problem:** `weight` was doing two jobs — controlling numeric scoring contribution AND implicitly signaling whether a source should run. This caused `is_available()=False` hack on venue_density and complaints_311 sitting at weight=0.3 despite being too thin/stale to score meaningfully. No clean path for corpus sources to deliver text to the RAG layer.

**Tried:** adjusting complaints_311 weight (0.3 → 0.1) — rejected as a quick hack, doesn't fix the underlying architectural confusion.

**Decided (with Luna):** Add `source_role: ClassVar[str]` to `NoiseSource` base class — values `"scoring"` | `"corpus"` | `"both"`. Pipeline separates them: scoring sources → score_engine → noise_scores table; corpus sources → reviews table (Sprint 2 consumes this). No weight=0 hacks needed anywhere.

**Changes:**
- complaints_311 → `source_role="corpus"`, weight removed from scoring
- osm_venues → `source_role="scoring"`, weight=0.6
- osm_roads → `source_role="scoring"`, weight=0.4
- venue_density → `source_role="corpus"`, `is_available()=False` hack removed
- yelp_reviews, reddit_posts → `source_role="corpus"` (already weight=0, now explicit)

---

## Sprint 3 — Conversational Agent + UI [CURRENT]

**Goal:** Live Streamlit app with Folium map + chat interface. User can click a neighborhood to read a pre-generated profile, or type a natural-language query ("find me a quiet neighborhood") and get a grounded answer from the Groq agent.

### Tasks

- [x] **3.1** Pre-generate profiles at pipeline time — run synthesizer for all 58 neighborhoods with venues, store `profile_text` in Supabase (profiles table + latest_profiles view). **58 profiles written, 5–22 chunks each. [DONE ✓ Apr 19]**
- [x] **3.2** Build LangChain agent (OpenAI gpt-4o-mini, swapped from Groq — see direction change below) and three tools: `rank_neighborhoods`, `get_profile`, `search_reviews`. **Agent live, 104/104 neighborhood profiles, nuanced grounded answers validated. [DONE ✓ Apr 21]**
- [x] **3.3** Streamlit UI — 4-tab dashboard (Map, Profiles, Compare & Temporal, Chat with MiaNoise) live on poc. Chat tab wired to 3.2 agent; input pinned at top, messages below. **[DONE ✓ Apr 21]**
- [ ] **3.4** End-to-end validation + prompt tuning
  - Run test queries through the live UI: "find me a quiet neighborhood", "is Wynwood loud on weekdays?", map click on Wynwood
  - Evaluate answer quality: grounded in data? cites score? concise? no hallucinated venues?
  - Iterate on system prompt (`agent/agent.py`) and tool descriptions (`agent/tools.py`) until answers are consistently correct and well-reasoned
  - Document what changed and why in `tasks/todo.md` direction changes

### Direction Changes — Sprint 3.3 (Apr 21)

**Floating FAB chat widget → Chat tab:**
- Tried: CSS `:has(> #marker) ~ sibling` selectors to position Streamlit elements as `position: fixed` overlay. DOM structure made reliable targeting impossible — tab content blocks and widget containers shared the same `stVerticalBlock` type, selectors misfired.
- Decided (with Luna): revert to dedicated "Chat with MiaNoise" tab. Input pinned at top of tab (never scrolls away); messages render below in reverse-chronological order so latest response is always closest to input.

### Direction Changes — Sprint 3.2 (confirmed Apr 21)

**Agent LLM: Groq → OpenAI gpt-4o-mini:**
- **Problem:** Groq free tier caps at 100K tokens/day. Agent loops re-send full context on every internal call (~5–7K tokens/question). 15–20 questions blows the cap. Dev tier unavailable.
- **Fix:** Switched to `ChatOpenAI(gpt-4o-mini)`. Consolidates on provider already used for embeddings + synthesis. Pennies at PoC scale, far higher limits.

**Profile coverage gap — 48 missing neighborhoods:**
- **Problem:** `generate_all_profiles()` iterated `reviews` table → only 58 neighborhoods with venue reviews got profiles. 48 quiet residential neighborhoods had no profile, breaking "find me a quiet neighborhood" queries.
- **Fix:** Changed to iterate `neighborhoods` table directly (all 104). Data-sparse neighborhoods get score-only profiles from composite score + source_scores. 104/104 now covered.

**Agent reliability fixes:**
- `_resolve_name()` — fuzzy name resolution: exact match → partial match → rank by review count (fixes "Brickell" → "Brickell Residential District" instead of "Brickell Village")
- System prompt rewritten to allow `get_profile` + `search_reviews` on same turn for timing-qualified questions
- Exception handling with explicit RateLimitError + GraphRecursionError user-facing messages

### Direction Changes — Sprint 3.1 (confirmed Apr 19)

**Geographic bleed bug:**
- **Problem:** `GooglePlacesReviews` used `_compute_radii()` (circumradius from centroid to polygon vertex) → Edgewater circumradius = 1205m, extending 640m into Wynwood. Edgewater profiles showed Wynwood venues (Perro Negro, The White Elephant, Barcelona Wine Bar).
- **Fix:** Rewrote to OSM venue-anchored search. Load OSM venue cache (`data/cache/osm_venues_miami.gpkg`), spatial join venues to neighborhood polygons (`predicate="within"`), search Google Places at each venue's exact coordinates with 100m radius. Neighborhood tag comes from spatial containment, not search geometry. 714 venues → 351 matched across 59 neighborhoods. Edgewater/Wynwood cleanly separated.
- **Also fixed:** `run_and_persist()` was missing `embed_all()` call between `write_corpus()` and `generate_all_profiles()`. All 58 initial profiles generated with 0 chunks. Fix: added `embed_all()` step in `pipeline.py`.

---

### Open Questions Carried Forward
- The UserWarning from `gpd.overlay` ("2684 dropped geometries of different geometry types") on osm_roads — likely MultiLineString/Point artifacts from intersection. Low priority but worth investigating before full version.

---

## Sprint 2 — RAG Pipeline [DONE ✓ confirmed Apr 19]

**Goal:** Given a neighborhood name, generate a natural-language noise profile grounded in review text.

### Tasks

- [x] **2.1** `google_places_reviews.fetch()` — 10,095 reviews across 58 neighborhoods → reviews table
- [x] **2.2** Reddit/Yelp dropped (see direction change below)
- [x] **2.3** Embedding — one review = one chunk, text-embedding-3-small, embeddings table (10,095 rows, no duplicates)
- [x] **2.4** Retrieval — pgvector cosine similarity via match_embeddings() RPC, multi-query merge
- [x] **2.5** Profile synthesis — GPT-4o-mini (replaced claude-sonnet; see direction change below)
- [x] **2.6** End-to-end test — Wynwood Industrial District profile verified, retrieval semantically correct

### Direction Change — Corpus Sources (confirmed Apr 19)

**Tried:** Yelp Fusion API → too expensive for PoC budget. Dropped.
**Tried:** Reddit PRAW API → Reddit locked API access behind formal builder approval in 2023. Dropped.
**Considered:** Reddit public JSON endpoints (no key, rate-limited) → viable as nice-to-have supplement, not core.
**Decided (with Luna):** Google Places reviews as sole primary corpus. Rationale:
- 714 OSM venues already mapped to neighborhoods — neighborhood tagging solved
- Places API New returns up to 5 reviews/venue → ceiling ~3,500 reviews
- Reviews for bars/nightclubs/restaurants naturally cover noise, hours, atmosphere
- Existing API key, no additional cost
- Reddit public JSON revisited if review volume is thin for specific neighborhoods

### Direction Change — LLM Stack (confirmed Apr 19)

**Tried:** Anthropic Claude (claude-sonnet-4-6) for profile synthesis → dropped.
**Considered:** Finetuning a custom LLM → rejected. Task is standard instruction-following that frontier models handle well out of the box; would require hundreds of labeled profiles to train on, ongoing retraining, and a hosted inference endpoint. Wrong tool for the job.
**Considered:** Anthropic Claude for live agent → rejected. Per-user API cost at scale; no reason to default to a paid closed-source model for a bounded query space.
**Decided (with Luna):**
- Profile synthesis (pipeline time): OpenAI GPT-4o-mini. Already in stack for embeddings, cheaper than Sonnet, sufficient for structured narrative generation.
- Live conversational agent: Groq free tier (Llama 3.1 70B). Zero per-query cost, 14,400 requests/day free, LangChain-native.
- Anthropic removed from stack entirely.

**Rationale:** Consolidate to one paid provider (OpenAI) for pipeline-time tasks; use free open-source inference (Groq) for live user-facing queries. Groq only fires when a user types — page loads and map clicks cost nothing.

### Open Questions (resolve before starting)
- **DATA GATE:** Is Google Places review volume and quality sufficient for a viable RAG corpus? Run exploration before implementing. (resolved Apr 19 — GO)
- Chunking strategy: fixed 512-token windows vs. sentence-boundary — which fits review content better? (resolved Apr 19 — one review = one chunk, venue context prepended)
