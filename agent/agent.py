"""
MiaNoise conversational agent.

Uses OpenAI gpt-4o-mini via LangChain 1.x create_agent (LangGraph-backed).
Three tools expose the full data layer: rank_neighborhoods, get_profile, search_reviews.

We originally used Groq Llama 3.3 70B (free tier) but hit the 100K-tokens/day cap
in casual testing — agent loops re-send full context on every internal LLM call,
so 15–20 user questions blew the cap. gpt-4o-mini consolidates on the provider
already used for embeddings + profile synthesis, costs pennies at PoC scale, and
has far higher rate limits. See tasks/lessons.md L16.

Entry point:
    from agent.agent import get_agent, ask
    agent = get_agent()
    reply = ask(agent, "Find me a quiet neighborhood", history=[])
    print(reply)
"""

import logging
import os

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agent.tools import TOOLS

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are MiaNoise, a neighborhood noise intelligence assistant for Miami renters.

You help users find neighborhoods that match their noise tolerance. All answers are grounded
in real data: composite noise scores (0.0 = silent, 1.0 = extremely loud) and review text
from bars, restaurants, and nightclubs across 58 Miami neighborhoods.

## Tool use rules

**get_profile** — call this FIRST for any question about a specific neighborhood by name.
The profile contains the composite score, source breakdown, and a narrative synthesized from
real reviews. It often already answers timing questions (night vs. day, weekday vs. weekend).

**search_reviews** — call this when the question has a specific timing or context angle
(e.g. "on Thursdays", "at night", "on weekends", "construction noise", "daytime").
Call it ON THE SAME TURN as get_profile when both apply — get_profile first, then search_reviews.
Skip it only if the profile already fully answers the timing question.

**rank_neighborhoods** — call this ONLY when the user asks to compare or rank multiple
neighborhoods (e.g. "find me a quiet area", "what are the noisiest neighborhoods?").
Do NOT call it for single-neighborhood questions.

## How to answer

Do not just repeat the profile. Use it as evidence, then write a direct answer to the
specific question asked. Example pattern:
  - Profile says: Thursday–Saturday nights are energetic, score 0.47
  - search_reviews returns: "TuCandela was nearly empty on a Thursday night"
  - Answer: "Brickell (score 0.47) gets loud Thursday through Saturday nights.
    That said, individual venues vary — TuCandela reviewers found it quiet on Thursdays.
    If nightlife noise is your concern, Sunday through Wednesday will be noticeably calmer."

## Rules

- Always cite the composite score when making a noise-level claim.
- Never invent venue names, hours, or noise claims not present in tool output.
- If a neighborhood has no data, say so clearly.
- 3–5 sentences. Answer the specific question asked, not a generic neighborhood overview."""


def get_agent():
    """
    Build and return a LangChain 1.x agent (LangGraph CompiledStateGraph).

    Returns:
        CompiledStateGraph — call via ask() or directly with
        agent.invoke({'messages': [...]})
    """
    llm = ChatOpenAI(
        model=MODEL,
        api_key=os.environ["OPENAI_API_KEY"],
        temperature=0.2,
    )
    return create_agent(llm, tools=TOOLS, system_prompt=SYSTEM_PROMPT, debug=False)


def ask(agent, user_input: str, history: list) -> tuple[str, list]:
    """
    Send one turn to the agent and return (reply_text, updated_history).

    Args:
        agent:      the compiled agent from get_agent()
        user_input: the user's message string
        history:    full message list from prior turns (all messages, including
                    intermediate tool call/result messages — returned by this function)

    Returns:
        (reply_text, new_history) — new_history is the full updated message list,
        suitable for passing back as history on the next turn.
    """
    messages = history + [HumanMessage(content=user_input)]
    try:
        result = agent.invoke({"messages": messages}, config={"recursion_limit": 16})
    except Exception as exc:
        logger.error("agent.ask error (%s): %s", type(exc).__name__, exc, exc_info=True)
        # Surface rate-limit errors explicitly so the user knows to wait
        if "429" in str(exc) or "rate" in str(exc).lower() or "RateLimit" in type(exc).__name__:
            return (
                "The AI service is temporarily rate-limited. "
                "Wait a few seconds and try again."
            ), history
        if "recursion" in str(exc).lower() or "GraphRecursion" in type(exc).__name__:
            return (
                "That question needed too many steps. Try asking about one neighborhood "
                "at a time, e.g. 'tell me about Brickell'."
            ), history
        return (
            "Sorry, something went wrong. Try rephrasing — e.g. 'tell me about Brickell' "
            "or 'what are the quietest neighborhoods?'"
        ), history

    # LangGraph returns the complete message list including tool call/result intermediates.
    # We preserve all of them so multi-turn context stays intact.
    all_messages = result["messages"]
    reply = all_messages[-1].content

    return reply, all_messages


if __name__ == "__main__":
    import logging
    from dotenv import load_dotenv

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    # Explicitly silence noisy third-party loggers regardless of prior handler state
    for _noisy in ("httpx", "httpcore", "groq", "openai", "supabase", "postgrest"):
        logging.getLogger(_noisy).setLevel(logging.ERROR)
    load_dotenv()

    agent = get_agent()
    print("\nMiaNoise Agent — type 'quit' to exit\n")
    history = []
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue
        reply, history = ask(agent, user_input, history)
        print(f"\nAgent: {reply}\n")
