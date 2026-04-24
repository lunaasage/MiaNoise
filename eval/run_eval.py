"""
MiaNoise RAGAS evaluation entry point.

Run from the project root:
    python3 -m eval.run_eval

What it does:
    1. For each of 15 test cases, retrieves relevant review chunks via pgvector
    2. Generates a focused answer using GPT-4o-mini (context-only, no hallucination)
    3. Runs RAGAS metrics: faithfulness, answer_relevancy, context_precision, context_recall
    4. Saves results to eval/results/ragas_report.json and eval/results/ragas_report.md

Prerequisites:
    - .env with SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY
    - Pipeline has been run (reviews embedded in Supabase)
    - pip install ragas==0.1.14 datasets  (already in requirements.txt)

Runtime: ~5–8 minutes (15 retrieval calls + 15 generations + RAGAS LLM calls)
Cost: ~$0.10–0.20 in OpenAI API calls
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv()

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
for _noisy in ("httpx", "httpcore", "openai", "supabase", "postgrest", "ragas"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


def main() -> None:
    from eval.runner import run_retrieval_and_generation
    from eval.report import run_ragas, save_report, print_summary

    print("MiaNoise — RAGAS Evaluation")
    print(f"{'=' * 60}")
    print("Step 1/3: Retrieving contexts and generating answers…\n")

    eval_data = run_retrieval_and_generation()

    print("\nStep 2/3: Running RAGAS metrics…")
    results = run_ragas(eval_data)

    print("\nStep 3/3: Saving reports…")
    save_report(results)
    print_summary(results)


if __name__ == "__main__":
    main()
