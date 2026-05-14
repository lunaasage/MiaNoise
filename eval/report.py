"""
RAGAS evaluation and report generation for MiaNoise.

Runs four RAGAS metrics against the retrieval + generation output:
  - faithfulness:       are all claims in the answer grounded in the contexts?
  - answer_relevancy:   does the answer address the question asked?
  - context_precision:  are the retrieved chunks ranked with relevant ones first?
  - context_recall:     do the contexts contain the facts needed to answer correctly?

Outputs:
  eval/results/ragas_report.json  — full per-question scores + aggregates
  eval/results/ragas_report.md    — human-readable summary for the presentation
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"

METRIC_DESCRIPTIONS = {
    "faithfulness": "Claims in the answer are grounded in retrieved review chunks (no hallucination)",
    "answer_relevancy": "The answer directly addresses the question asked",
    "context_precision": "Retrieved chunks are relevant to the question (signal-to-noise ratio)",
    "context_recall": "Retrieved chunks contain the facts needed to give a correct answer",
}

SCORE_LABELS = {
    (0.0, 0.5): "⚠️  Needs improvement",
    (0.5, 0.7): "🟡 Acceptable",
    (0.7, 0.85): "🟢 Good",
    (0.85, 1.01): "✅ Excellent",
}


def _score_label(score: float) -> str:
    for (lo, hi), label in SCORE_LABELS.items():
        if lo <= score < hi:
            return label
    return "—"


def run_ragas(eval_data: dict) -> dict:
    """
    Run RAGAS evaluation metrics and return structured results.

    Args:
        eval_data: output of runner.run_retrieval_and_generation()

    Returns:
        dict with 'aggregate' scores and 'per_question' list
    """
    from ragas import evaluate, EvaluationDataset, SingleTurnSample
    from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall

    metadata = eval_data.pop("metadata")  # not part of RAGAS schema

    # Filter out zero-chunk cases — empty contexts skew faithfulness/precision metrics.
    # These are reported separately in the output as "no retrieval data".
    valid_indices = [i for i, m in enumerate(metadata) if m["has_data"]]
    skipped = [metadata[i] for i in range(len(metadata)) if not metadata[i]["has_data"]]
    if skipped:
        print(f"\n  ⚠️  Skipping {len(skipped)} case(s) with 0 retrieved chunks (no embeddings for neighborhood):")
        for s in skipped:
            print(f"     - [{s['neighborhood']}] {s['question'][:70]}")

    if not valid_indices:
        raise RuntimeError("All test cases returned 0 chunks — check that embed_all() has been run.")

    samples = [
        SingleTurnSample(
            user_input=eval_data["question"][i],
            response=eval_data["answer"][i],
            retrieved_contexts=eval_data["contexts"][i],
            reference=eval_data["ground_truth"][i],
        )
        for i in valid_indices
    ]
    dataset = EvaluationDataset(samples=samples)

    n_valid = len(valid_indices)
    print(f"\nRunning RAGAS evaluation (4 metrics × {n_valid} questions)…")
    result = evaluate(
        dataset,
        metrics=[Faithfulness(), AnswerRelevancy(), ContextPrecision(), ContextRecall()],
        raise_exceptions=False,
    )

    # Extract per-question scores (valid cases only)
    result_df = result.to_pandas()
    per_question = []
    for df_idx, orig_idx in enumerate(valid_indices):
        row = result_df.iloc[df_idx]
        per_question.append({
            "neighborhood": metadata[orig_idx]["neighborhood"],
            "question": metadata[orig_idx]["question"],
            "chunk_count": metadata[orig_idx]["chunk_count"],
            "faithfulness": round(float(row.get("faithfulness", 0)), 4),
            "answer_relevancy": round(float(row.get("answer_relevancy", 0)), 4),
            "context_precision": round(float(row.get("context_precision", 0)), 4),
            "context_recall": round(float(row.get("context_recall", 0)), 4),
            "answer_preview": eval_data["answer"][orig_idx][:200] + "…",
        })

    # Append skipped cases to per_question with null scores for reporting
    for s in skipped:
        per_question.append({
            "neighborhood": s["neighborhood"],
            "question": s["question"],
            "chunk_count": 0,
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": None,
            "context_recall": None,
            "answer_preview": "(skipped — no retrieval data)",
        })

    metric_keys = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    aggregate = {
        k: round(
            sum(q[k] for q in per_question if q[k] is not None)
            / max(1, sum(1 for q in per_question if q[k] is not None)),
            4,
        )
        for k in metric_keys
    }

    return {"aggregate": aggregate, "per_question": per_question}


def save_report(results: dict) -> None:
    """Save JSON + Markdown reports to eval/results/."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── JSON ──────────────────────────────────────────────────────────────
    json_path = RESULTS_DIR / "ragas_report.json"
    full_report = {"timestamp": timestamp, **results}
    with open(json_path, "w") as f:
        json.dump(full_report, f, indent=2)
    print(f"\nJSON report saved → {json_path}")

    # ── Markdown ───────────────────────────────────────────────────────────
    agg = results["aggregate"]
    pq = results["per_question"]

    lines = [
        "# MiaNoise — RAGAS Evaluation Report",
        f"\n_Generated: {timestamp}_",
        f"\n**Test cases:** {len(pq)} questions across {len({q['neighborhood'] for q in pq})} neighborhoods",
        "\n---\n",
        "## Aggregate Scores\n",
        "| Metric | Score | Rating | What it measures |",
        "|---|---|---|---|",
    ]
    for key, desc in METRIC_DESCRIPTIONS.items():
        score = agg[key]
        lines.append(f"| {key.replace('_', ' ').title()} | **{score:.3f}** | {_score_label(score)} | {desc} |")

    lines += [
        "\n---\n",
        "## Per-Question Results\n",
        "| # | Neighborhood | Chunks | Faith. | Rel. | Prec. | Recall |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, q in enumerate(pq, 1):
        def _fmt(v):
            return f"{v:.2f}" if v is not None else "—"
        lines.append(
            f"| {i} | {q['neighborhood']} | {q['chunk_count']} "
            f"| {_fmt(q['faithfulness'])} | {_fmt(q['answer_relevancy'])} "
            f"| {_fmt(q['context_precision'])} | {_fmt(q['context_recall'])} |"
        )

    lines += [
        "\n---\n",
        "## Methodology\n",
        "- **Retrieval:** multi-query pgvector cosine similarity (text-embedding-3-small, 5 queries × top-4 chunks, deduplicated)",
        "- **Generation:** GPT-4o-mini with strict context-only instruction (no external knowledge)",
        "- **Evaluation:** RAGAS v0.2 LLM-based metrics (GPT-4o-mini as judge)",
        "- **Test set:** 15 hand-crafted questions covering loud/quiet/temporal/renter-decision query types",
        "\n---\n",
        "_MiaNoise — Miami neighborhood noise intelligence for renters_",
    ]

    md_path = RESULTS_DIR / "ragas_report.md"
    with open(md_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Markdown report saved → {md_path}")


def print_summary(results: dict) -> None:
    """Print a concise summary to stdout."""
    agg = results["aggregate"]
    print("\n" + "=" * 60)
    print("  MiaNoise RAGAS Evaluation — Summary")
    print("=" * 60)
    for key in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        score = agg[key]
        label = _score_label(score)
        print(f"  {key.replace('_', ' ').title():25s}  {score:.3f}  {label}")
    print("=" * 60)

    low = [q for q in results["per_question"] if q["faithfulness"] < 0.5]
    if low:
        print(f"\n  ⚠️  {len(low)} question(s) with faithfulness < 0.5 (potential hallucination):")
        for q in low:
            print(f"     - [{q['neighborhood']}] {q['question'][:70]}")
    print()
