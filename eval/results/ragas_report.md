# MiaNoise — RAGAS Evaluation Report

_Generated: 2026-04-28T00:29:03Z_

**Test cases:** 15 questions across 10 neighborhoods

---

## Aggregate Scores

| Metric | Score | Rating | What it measures |
|---|---|---|---|
| Faithfulness | **0.860** | ✅ Excellent | Claims in the answer are grounded in retrieved review chunks (no hallucination) |
| Answer Relevancy | **0.446** | ⚠️  Needs improvement | The answer directly addresses the question asked |
| Context Precision | **0.651** | 🟡 Acceptable | Retrieved chunks are relevant to the question (signal-to-noise ratio) |
| Context Recall | **0.612** | 🟡 Acceptable | Retrieved chunks contain the facts needed to give a correct answer |

---

## Per-Question Results

| # | Neighborhood | Chunks | Faith. | Rel. | Prec. | Recall |
|---|---|---|---|---|---|---|
| 1 | Wynwood Industrial District | 6 | 1.00 | 0.99 | 0.81 | 0.67 |
| 2 | Wynwood Industrial District | 7 | 0.80 | 0.99 | 0.37 | 1.00 |
| 3 | CBD | 9 | 1.00 | 0.93 | 0.48 | 0.25 |
| 4 | Brickell Village | 12 | 0.90 | 0.00 | 0.40 | 0.75 |
| 5 | Brickell Village | 10 | 1.00 | 0.00 | 0.33 | 0.25 |
| 6 | Wynwood Industrial District | 7 | 0.60 | 0.94 | 1.00 | 0.60 |
| 7 | Flagami | 8 | 0.67 | 0.99 | 0.33 | 0.33 |
| 8 | Edgewater | 7 | 1.00 | 0.00 | 0.81 | 0.67 |
| 9 | East Little Havana | 9 | 1.00 | 0.00 | 0.88 | 0.67 |
| 10 | Design District | 7 | 0.71 | 0.00 | 0.58 | 0.50 |
| 11 | Midtown | 10 | 0.75 | 0.00 | 0.46 | 0.33 |
| 12 | Grove Center | 10 | 1.00 | 0.00 | 0.97 | 0.75 |
| 13 | Brickell Village | 10 | 0.67 | 1.00 | 0.88 | 1.00 |
| 14 | Allapattah Industrial District | 4 | 0.80 | 0.00 | 1.00 | 0.67 |
| 15 | CBD | 9 | 1.00 | 0.86 | 0.48 | 0.75 |

---

## Methodology

- **Retrieval:** multi-query pgvector cosine similarity (text-embedding-3-small, 5 queries × top-4 chunks, deduplicated)
- **Generation:** GPT-4o-mini with strict context-only instruction (no external knowledge)
- **Evaluation:** RAGAS v0.2 LLM-based metrics (GPT-4o-mini as judge)
- **Test set:** 15 hand-crafted questions covering loud/quiet/temporal/renter-decision query types

---

_MiaNoise — Miami neighborhood noise intelligence for renters_