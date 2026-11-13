"""Runtime knobs for the AI layer.

Every knob is optional: a Django setting wins, then an environment variable (.env), then the default below.
That keeps the Day 6 agents configurable without touching config/settings/base.py.

    AI_TOOL_TRANSPORT         mcp (default: MCP over SSE, falls back to direct calls and says so in the trace)
                              mcp_only (fail the run if the MCP server is unreachable) | direct (never use MCP)
    AI_MCP_TIMEOUT            seconds allowed for one MCP batch (default 15, plus 0.2 s per call)
    AI_RAG_BUDGET_SECONDS     time allowed for vector search across all pairs of one run (default 20);
                              after that the remaining pairs use the graph part of RAG only
    CLINICAL_NOTES_USE_LLM    true -> local Ollama extracts condition phrases from redacted notes (default false)
    ADVISORY_USE_LLM          true -> an LLM may re-phrase the summaries; output is validated, else the template stays
    ADVISORY_LLM_LOCAL        true -> use the local Ollama model for that re-phrasing instead of the cloud model
"""
import os

from django.conf import settings

_TRUE = {"1", "true", "yes", "on"}


def setting(name: str, default=None):
    if hasattr(settings, name):
        return getattr(settings, name)
    raw = os.environ.get(name)
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw.strip().lower() in _TRUE
    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError:
            return default
    if isinstance(default, int):
        try:
            return int(raw)
        except ValueError:
            return default
    return raw