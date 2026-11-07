from .common import traced


def run(state: dict) -> dict:
    """TODO (lead): for each drug pair -> check_interaction (MCP) + retrieve label chunks (RAG).
    Each finding must carry evidence: [{"type": "interaction"|"chunk", "id": ..., "source": ...}]."""
    trace: list = []
    with traced(trace, "drug_interaction", 3, f"{len(state.get('resolved_drugs', []))} drugs") as t:
        findings: list[dict] = []
        t["output_summary"] = f"{len(findings)} findings (stub)"
    return {"findings": findings, "trace": trace}
