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
