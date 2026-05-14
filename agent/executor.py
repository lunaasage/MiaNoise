"""
MiaNoise agent executor — stable interface for the Streamlit UI.

Thin wrapper around agent.agent so app.py imports one place and
the internals can change without touching the UI.
"""

from agent.agent import ask, get_agent

__all__ = ["get_agent", "ask"]
