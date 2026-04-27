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
    - ragas>=0.2,<0.3 installed (in requirements.txt)

Runtime: ~5–8 minutes (15 retrieval calls + 15 generations + RAGAS LLM calls)
Cost: ~$0.10–0.20 in OpenAI API calls
"""

# ── Python 3.14 + nest_asyncio compatibility fix ──────────────────────────────
# nest_asyncio.apply() (called at RAGAS import time) corrupts asyncio.current_task()
# on Python 3.14, which causes asyncio.timeout() to raise "Timeout should be used
# inside a task" on every metric evaluation job. Blocking nest_asyncio before any
# RAGAS import preserves correct task tracking and lets evaluation complete normally.
import sys as _sys
import types as _types
_fake_nest = _types.ModuleType("nest_asyncio")
_fake_nest.apply = lambda *args, **kwargs: None
_sys.modules.setdefault("nest_asyncio", _fake_nest)
# ──────────────────────────────────────────────────────────────────────────────

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
