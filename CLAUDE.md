# MiaNoise — Claude Code Context

## What This Project Is
MiaNoise is an LLM-powered neighborhood noise intelligence tool for Miami renters.
It synthesizes heterogeneous urban data (311 complaints, nightlife density, traffic,
flight paths, crowd-sourced reviews) into natural-language neighborhood profiles
queryable via a conversational agent.

The final product is a shareable public Streamlit dashboard with:
- An interactive Folium/Pydeck map with color-coded noise score choropleth
- A chat interface powered by a LangChain agent
- Click-to-profile: neighborhood click → RAG-generated narrative

---

## Two Versions — One Codebase
This repo serves two timelines:

| Version | Branch | Deadline | Scope |
|---|---|---|---|
| PoC | `poc` | April 29, 2026 | 311 complaints + venue density + Yelp/Reddit reviews |
| Full | `main` | Post-April 29 | All PoC sources + TomTom traffic + FAA flight paths + construction permits |

The architecture is identical across both. The only difference is data coverage.
The score engine computes from whatever sources are active — new sources plug in
without touching pipeline logic.

---

## Core Architecture Principle
Every noise data source is a plugin. Each lives in `ingestion/sources/` and inherits
from `NoiseSource` (defined in `ingestion/sources/base.py`). If a source's required
API keys are missing from `.env`, it returns `None` gracefully and the pipeline
continues with remaining sources. This means the PoC runs on 2 sources and the full
version runs on 6+ — same code, no rewriting.

---

## Folder Structure
```
mianoise/
├── ingestion/
│   ├── sources/
│   │   ├── base.py              # NoiseSource abstract base class
│   │   ├── complaints_311.py    # Miami Open Data — 311 noise complaints (PoC)
│   │   ├── venue_density.py     # Google Places — nightlife/bar density (PoC)
│   │   ├── tomtom_traffic.py    # TomTom — traffic volume (full version)
│   │   ├── opensky_flights.py   # OpenSky — flight path frequency (full version)
│   │   └── construction.py     # Miami Open Data — permits (full version)
│   ├── score_engine.py          # Weighted composite score computation
│   └── pipeline.py              # Orchestrates all active sources
├── rag/                         # Embedding, retrieval, profile synthesis
├── agent/                       # LangChain AgentExecutor + tools
├── ui/                          # Streamlit app + Folium map
├── eval/                        # RAGAS evaluation framework
├── data/geojson/                # Miami neighborhood boundary GeoJSON
├── tests/
├── .env.example
├── requirements.txt
├── ARCHITECTURE.md
└── README.md
```

---

## Tech Stack
| Layer | Tool |
|---|---|
| Database | Supabase (PostgreSQL + pgvector) |
| Embeddings | OpenAI text-embedding-3-small |
| LLM Synthesis | Claude claude-sonnet-4-20250514 |
| Agent | LangChain AgentExecutor |
| Evaluation | RAGAS |
| Frontend | Streamlit + Folium/Pydeck |
| Scheduling | n8n (nightly data refresh) |
| Version Control | GitHub (branches: `main`, `poc`) |

---

## Data Sources

### PoC — Active on `poc` branch
| Source | API | What it provides |
|---|---|---|
| Miami 311 complaints | Miami Open Data Portal | Historical noise complaint density per neighborhood |
| Venue density | Google Places API | Bar, club, restaurant count per area |
| Reviews | Yelp Fusion API | Business review text for RAG corpus |
| Community posts | Reddit API (PRAW) | r/miami, r/MiamiBeach noise anecdotes |

### Full Version — Placeholders exist, activate via `.env`
| Source | API | What it provides |
|---|---|---|
| Traffic volume | TomTom Traffic API | Road noise proxy by segment |
| Flight paths | OpenSky Network | Overflight frequency over Miami neighborhoods |
| Construction | Miami Open Data Portal | Active permit locations by zone |

---

## Noise Score Formula
Composite score = weighted sum of normalized (0–1) signals per neighborhood.
Weights are adjustable and documented in `ingestion/score_engine.py`.

- **PoC weights**: 311 complaints (0.3) + OSM venue density (0.5) + OSM road noise (0.2)
- **Full version weights**: to be calibrated once all sources are active

Score is computed at ingestion time and stored in Supabase. The RAG layer then
explains *why* a neighborhood has that score using retrieved review text.

---

## Sprint Plan (PoC Branch)
| Sprint | Dates | Focus | Key Output |
|---|---|---|---|
| Sprint 0 | Apr 3–5 | Infrastructure & architecture | Repo, schema, API keys, GeoJSON |
| Sprint 1 | Apr 6–9 | Data ingestion + score engine | Composite noise scores per neighborhood |
| Sprint 2 | Apr 10–13 | RAG pipeline | LLM-generated neighborhood profiles |
| Sprint 3 | Apr 14–17 | Conversational agent + UI | Live Streamlit app with map + chat |
| Sprint 4 | Apr 18–21 | Evaluation + polish | RAGAS report, shareable URL |
| Sprint 5 | Apr 22–28 | Presentation prep | Slide deck + live demo |

---

## Current Status
- **Branch**: `poc`
- **Sprint**: 2 [CURRENT]
- **Sprint 1**: DONE (confirmed Apr 19) — pipeline runs end-to-end, 104 neighborhoods scored, data in Supabase
- **Next**: RAG corpus (`yelp_reviews`, `reddit_posts`), embed with OpenAI text-embedding-3-small, store in `embeddings` table, build retrieval + LLM synthesis for neighborhood profiles

### Key Files
| File | Role | Sprint | Status |
|---|---|---|---|
| `ingestion/db.py` | Supabase I/O (seed, write_scores, load GDF/centroids) | 1 | Active |
| `ingestion/sources/complaints_311.py` | City of Miami 311 NOISEVIO scoring (weight=0.3) | 1 | Active |
| `ingestion/sources/osm_venues.py` | OSM venue density scoring (weight=0.5) | 1 | Active |
| `ingestion/sources/osm_roads.py` | OSM weighted road-km scoring (weight=0.2) | 1 | Active |
| `ingestion/pipeline.py` | Orchestrator + `run_and_persist()` entry point | 1 | Active |
| `ingestion/score_engine.py` | Weighted composite score computation | 0 | Active |
| `ingestion/sources/base.py` | `NoiseSource` ABC + `NeighborhoodScore` dataclass | 0 | Active |
| `migrations/001_initial_schema.sql` | Supabase DDL (neighborhoods, noise_scores, reviews, embeddings) | 0 | Active |
| `data/geojson/miami_neighborhoods.geojson` | 106 neighborhood polygons (WGS84) | 0 | Active |
| `ingestion/sources/venue_density.py` | Google Places — deferred to Sprint 2, weight=0, disabled | 1 | Inactive |

> NEVER update sprint status or this table without Luna's explicit confirmation (Sprint Completion Protocol above).

---

## Conventions
- Never modify `pipeline.py` to hardcode a specific source — all sources plug in via base class
- Every source file must implement `is_available()` and `fetch()`
- All API keys live in `.env` only — never hardcoded, never committed
- Commit message format: `type: description` (types: `chore`, `feat`, `fix`, `docs`)
- Branch `poc` is the working branch until April 29 — do not merge to `main` until PoC is complete

### Sprint Completion Protocol (MANDATORY)
When a sub-sprint or sprint is finished, DO NOT update status unilaterally. Ask Luna two things:
1. "Can I mark [sub-sprint/sprint] as done?"
2. "Which files should I log in the Key Files table? Here are my candidates: [list]"

On confirmation:
1. Check off the sprint, update status labels (CURRENT → DONE)
2. Update the Key Files table — add new outputs, remove superseded files
3. Update the Change Log
4. Update ARCHITECTURE.md for any new or modified modules

### Lessons Tracking
- `tasks/lessons.md` — updated after every correction or unexpected finding. Read at session start.
- `tasks/todo.md` — current sprint task list. Updated when direction changes are confirmed.

### No Guessing
- Never hardcode a value that can be queried or derived
- When data behaves unexpectedly (zero rows, wrong geography, stale dates): investigate before assuming the code is wrong
- Surface unexpected findings to Luna rather than patching around them

---

## Change Log
| Date | Sprint | Change | Rationale |
|---|---|---|---|
| Apr 17, 2026 | 0 | Initialized repo structure + CLAUDE.md | Foundation before any pipeline code |
| Apr 17, 2026 | 0 | `NoiseSource` ABC, `NeighborhoodScore`, all 7 source stubs, `ALL_SOURCES` registry | Plugin architecture so PoC and full version share one codebase with no branching logic |
| Apr 17, 2026 | 0 | `score_engine.py` — weighted composite score computation | Separates score math from orchestration; zero-weight sources skip numeric score cleanly |
| Apr 17, 2026 | 0 | `pipeline.py` — registry-driven orchestrator | Discovers sources via `ALL_SOURCES`; adding a source never requires touching this file |
| Apr 17, 2026 | 0 | `migrations/001_initial_schema.sql` — Supabase DDL | Defines neighborhoods, noise_scores, reviews, embeddings tables + RLS + pgvector index |
| Apr 17, 2026 | 0 | `data/geojson/miami_neighborhoods.geojson` — 106 polygons | City of Miami ArcGIS Hub; seeds `neighborhoods` table and drives the Folium choropleth |
| Apr 17, 2026 | 0 | `requirements.txt`, `.env.example`, `ARCHITECTURE.md` | Dependency pinning, credential documentation, and module-level architecture reference |
| Apr 17, 2026 | 1 | `ingestion/db.py` — Supabase I/O layer | Centralizes all DB reads/writes so sources never construct clients directly |
| Apr 17, 2026 | 1 | `complaints_311.fetch()` — ArcGIS REST + spatial join | Miami-Dade portal migrated from Socrata to ArcGIS; geopandas sjoin assigns complaints to polygons |
| Apr 17, 2026 | 1 | `venue_density.fetch()` — Google Places + per-neighborhood radius | Per-neighborhood circumradius (UTM 17N, capped 1500m) chosen over fixed 800m due to Miami's uneven neighborhood sizes |
| Apr 17, 2026 | 1 | `run_and_persist()` + `__main__` in pipeline.py | Keeps `run_pipeline()` pure/testable; persistence is a separate entry point |
| Apr 17, 2026 | 1 | `SUPABASE_SERVICE_KEY` added to `.env.example` | Anon key is read-only (RLS); service role key required for ingestion writes |
| Apr 17, 2026 | 1 | `osm_venues.py` — OSMVenueDensity (weight=0.5) | OSM Overpass returns every mapped venue in Miami — 3–5× more complete than Google Places, no API key, no quota |
| Apr 17, 2026 | 1 | `osm_roads.py` — OSMRoadNoise (weight=0.2) | OSM weighted road-km replaces TomTom for PoC; motorway×3.0 → primary×1.0 weights reflect dB contribution; clipped to neighborhood polygons in UTM 17N |
| Apr 17, 2026 | 1 | `complaints_311.py` rewritten to City of Miami 311 NOISEVIO (weight=0.3) | Miami-Dade 311 has no noise category; Code Compliance violations are geographically mismatched (lat 25.51–25.72 vs. City of Miami lat 25.73–25.85) |
| Apr 17, 2026 | 1 | `venue_density.py` weight 1.0 → 0.0 | OSMVenueDensity takes over primary venue scoring; Google Places deferred to Sprint 2 for cross-validation |

---

## North Star
The project is done when a stranger can open the link, click on Wynwood, and read:

> *"Wynwood is loud on Friday and Saturday nights until 3–4am, driven by club and bar
> activity on NW 2nd Ave. Daytime noise is moderate, primarily construction-related.
> Residents on Reddit describe it as 'a great place to go out, not a great place to sleep.'"*

— and trust that the LLM said that because the data supports it.
