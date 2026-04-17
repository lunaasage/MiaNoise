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

- **PoC weights**: 311 complaints (0.5) + venue density (0.5)
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
- **Sprint**: 2 (starting)
- **Completed (Sprint 1)**: `ingestion/db.py` (Supabase client, seed_neighborhoods, write_scores, centroid/GDF loaders), `complaints_311.fetch()` (ArcGIS REST + geopandas spatial join + max-normalization), `venue_density.fetch()` (Google Places Nearby Search + per-neighborhood circumradius in UTM 17N + max-normalization), `run_and_persist()` + `__main__` in pipeline.py, `SUPABASE_SERVICE_KEY` in `.env.example`
- **Next**: implement `yelp_reviews.fetch()` and `reddit_posts.fetch()` (RAG corpus text), embed review chunks with OpenAI text-embedding-3-small, store in Supabase `embeddings` table, build RAG retrieval function and LLM synthesis to generate neighborhood profiles

> Update this section at the end of every sprint.

---

## Conventions
- Never modify `pipeline.py` to hardcode a specific source — all sources plug in via base class
- Every source file must implement `is_available()` and `fetch()`
- All API keys live in `.env` only — never hardcoded, never committed
- Commit message format: `type: description` (types: `chore`, `feat`, `fix`, `docs`)
- Branch `poc` is the working branch until April 29 — do not merge to `main` until PoC is complete
- At the end of every sprint, before committing: 
    1. Update ARCHITECTURE.md with every file built or modified — what it does, what it exports, how it connects to other modules
    2. Update the Current Status section in CLAUDE.md with the completed sprint and next sprint
    3. Update the Change Log table with date, sprint, change, and rationale

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

---

## North Star
The project is done when a stranger can open the link, click on Wynwood, and read:

> *"Wynwood is loud on Friday and Saturday nights until 3–4am, driven by club and bar
> activity on NW 2nd Ave. Daytime noise is moderate, primarily construction-related.
> Residents on Reddit describe it as 'a great place to go out, not a great place to sleep.'"*

— and trust that the LLM said that because the data supports it.
