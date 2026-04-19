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

### Open Questions Carried Forward
- The UserWarning from `gpd.overlay` ("2684 dropped geometries of different geometry types") on osm_roads — likely MultiLineString/Point artifacts from intersection. Low priority but worth investigating before full version.

---

## Sprint 2 — RAG Pipeline [CURRENT]

**Goal:** Given a neighborhood name, generate a natural-language noise profile grounded in review text.

### Tasks

- [ ] **2.1** Implement `yelp_reviews.fetch()` — pull review text for bars/nightclubs/restaurants near each neighborhood; store in `reviews` table
- [ ] **2.2** Implement `reddit_posts.fetch()` — search r/miami, r/MiamiBeach for noise-related posts; store in `reviews` table
- [ ] **2.3** Chunking + embedding — ~512-token chunks, embed with `text-embedding-3-small`, store in `embeddings` table
- [ ] **2.4** Retrieval function — given neighborhood + query, top-k chunks via pgvector cosine similarity
- [ ] **2.5** Profile synthesis — claude-sonnet + retrieved chunks + composite score → neighborhood noise narrative
- [ ] **2.6** End-to-end test — run for Wynwood, verify output matches North Star

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

### Open Questions (resolve before starting)
- **DATA GATE:** Is Google Places review volume and quality sufficient for a viable RAG corpus? Run exploration before implementing. (in progress)
- Chunking strategy: fixed 512-token windows vs. sentence-boundary — which fits review content better?
