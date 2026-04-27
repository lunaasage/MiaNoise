# MiaNoise — RAGAS Evaluation Report

_Generated: 2026-04-27T22:48:54Z_

**Test cases:** 15 questions across 10 neighborhoods

---

## Aggregate Scores

| Metric | Score | Rating | What it measures |
|---|---|---|---|
| Faithfulness | **0.847** | 🟢 Good | Claims in the answer are grounded in retrieved review chunks (no hallucination) |
| Answer Relevancy | **0.321** | ⚠️  Needs improvement | The answer directly addresses the question asked |
| Context Precision | **0.347** | ⚠️  Needs improvement | Retrieved chunks are relevant to the question (signal-to-noise ratio) |
| Context Recall | **0.322** | ⚠️  Needs improvement | Retrieved chunks contain the facts needed to give a correct answer |

---

## Per-Question Results

| # | Neighborhood | Chunks | Faith. | Rel. | Prec. | Recall |
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

---

## Methodology

- **Retrieval:** multi-query pgvector cosine similarity (text-embedding-3-small, 5 queries × top-4 chunks, deduplicated)
- **Generation:** GPT-4o-mini with strict context-only instruction (no external knowledge)
- **Evaluation:** RAGAS v0.1.14 LLM-based metrics (GPT-4o-mini as judge)
- **Test set:** 15 hand-crafted questions covering loud/quiet/temporal/renter-decision query types

---

_MiaNoise — Miami neighborhood noise intelligence for renters_