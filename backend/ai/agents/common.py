import re
import time
from contextlib import contextmanager


@contextmanager
def traced(trace: list, agent_name: str, step_order: int, input_summary: str = ""):
    """Append one AgentTrace-shaped dict to `trace` (the graph persists it to AgentTrace rows)."""
    entry = {"agent_name": agent_name, "step_order": step_order, "input_summary": input_summary,
             "output_summary": "", "tool_calls": [], "latency_ms": 0}
    t0 = time.perf_counter()
    try:
        yield entry
    finally:
        entry["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        trace.append(entry)


# A strength written on its own ("500", "500 mg", "0.5 g") but NOT a number glued to a name ("Vitamin B12").
_STRENGTH = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ug|g|ml|iu|%)?(?![A-Za-z0-9])", re.IGNORECASE)


def safe_label(text: str, fallback: str = "unnamed item") -> str:
    """Display name without strengths. Strengths are removed on purpose: they look like dosing to the output
    guardrail, and summaries must never carry dose-like text."""
    cleaned = _STRENGTH.sub(" ", text or "")
    cleaned = re.sub(r"[\s,;:/()\[\]]+", " ", cleaned).strip(" .-")
    return cleaned or fallback


def med_label(med: dict) -> str:
    return safe_label(med.get("brand_name") or med.get("raw_text") or "")


def ellipsize(text: str, limit: int) -> str:
    """Collapse whitespace and cut at a word boundary."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.- ")
    return f"{cut}…"


def with_period(text: str) -> str:
    text = (text or "").rstrip()
    return text if not text or text[-1] in ".!?…।" else f"{text}."