from ..guardrails.output_checks import check_output
from .common import traced


def run(state: dict) -> dict:
    """TODO (lead): re-check every finding via check_interaction (MCP, independent of the LLM wording) and label it
    verified / unverified / conflict. Then enforce the output guardrail."""
    trace: list = []
    with traced(trace, "verifier", 5, f"{len(state.get('findings', []))} findings") as t:
        findings = [{**f, "verification_status": f.get("verification_status", "unverified")}
                    for f in state.get("findings", [])]
        text = " ".join(str(v) for v in state.get("summaries", {}).values())
        violations = check_output(summary_text=text, findings=findings)
        t["output_summary"] = f"violations={violations or 'none'} (stub verification)"
    return {"findings": findings, "violations": violations, "trace": trace}
