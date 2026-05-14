"""
RAGAS evaluation runner for MiaNoise.

For each test case:
  1. Retrieves relevant review chunks from the RAG pipeline (multi-query)
  2. Generates a focused answer using GPT-4o-mini grounded in those chunks
  3. Returns structured data ready for RAGAS evaluation

Evaluates the RAG pipeline (retriever + generation) directly rather than the
full agent, so faithfulness and context quality metrics are clean and interpretable.
"""

import logging
import os
import sys
from pathlib import Path

# Ensure project root is on path when run directly
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

from rag.retriever import retrieve_multi_query
from eval.dataset import TEST_CASES

logger = logging.getLogger(__name__)

GENERATION_MODEL = "gpt-4o-mini"
RETRIEVAL_QUERIES = [
    "{question}",
    "noise levels at night",
    "loud music bars clubs nightlife",
    "quiet peaceful residential",
    "traffic street noise daytime",
]
TOP_K_PER_QUERY = 4  # 4 queries × 4 = up to 16 chunks, deduped to ~8–12


def _generation_queries(question: str) -> list[str]:
    """Expand a question into multiple retrieval queries for broader context coverage."""
    return [q.format(question=question) for q in RETRIEVAL_QUERIES]


def generate_answer(question: str, neighborhood: str, contexts: list[str]) -> str:
    """
    Generate a focused answer to a specific question using only the provided contexts.

    Deliberately constrained to context only — faithfulness metric requires that
    every claim in the answer is grounded in the retrieved chunks.
    """
    if not contexts:
        return (
            f"Limited data is available for {neighborhood}. "
            "No review excerpts were found matching this question. "
            "A low or zero noise score for this area may indicate fewer mapped venues "
            "and noise complaints, which can itself suggest a quieter character."
        )

    context_text = "\n\n".join(f'• "{c}"' for c in contexts[:10])  # cap at 10 chunks

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a noise intelligence assistant for Miami neighborhoods. "
                    "Answer the user's question using ONLY the provided review excerpts. "
                    "Every claim you make must be directly supported by a review excerpt. "
                    "Do not add general knowledge about the neighborhood. "
                    "Be specific, cite evidence, and keep the answer to 3–4 sentences."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Neighborhood: {neighborhood}\n\n"
                    f"Review excerpts:\n{context_text}\n\n"
                    f"Question: {question}"
                ),
            },
        ],
    )
    return response.choices[0].message.content.strip()


def run_retrieval_and_generation() -> dict:
    """
    Run retrieval + generation for all test cases.

    Returns a dict with lists ready for RAGAS Dataset.from_dict():
        {
            "question": [...],
            "answer": [...],
            "contexts": [[...], ...],  # list of lists
            "ground_truth": [...],
        }
    Also returns a "metadata" key with per-case info (neighborhood, chunk counts)
    for the report.
    """
    questions, answers, contexts_list, ground_truths, metadata = [], [], [], [], []

    for i, case in enumerate(TEST_CASES, 1):
        neighborhood = case["neighborhood"]
        question = case["question"]
        ground_truth = case["ground_truth"]

        logger.info(
            "eval [%d/%d] %s — %s",
            i, len(TEST_CASES), neighborhood, question[:60],
        )
        print(f"  [{i:2}/{len(TEST_CASES)}] {neighborhood}: {question[:70]}…")

        queries = _generation_queries(question)
        chunks = retrieve_multi_query(neighborhood, queries, top_k_per_query=TOP_K_PER_QUERY)

        answer = generate_answer(question, neighborhood, chunks)

        questions.append(question)
        answers.append(answer)
        # Keep empty-chunk cases in output for reporting, but flag them.
        # report.py filters these out of RAGAS metrics to avoid placeholder skew.
        contexts_list.append(chunks)
        ground_truths.append(ground_truth)
        metadata.append({
            "neighborhood": neighborhood,
            "chunk_count": len(chunks),
            "question": question,
            "has_data": len(chunks) > 0,
        })

    return {
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths,
        "metadata": metadata,
    }
