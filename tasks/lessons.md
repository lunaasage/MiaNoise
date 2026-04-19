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

## Sprint 2

*(to be filled)*
