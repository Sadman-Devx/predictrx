from .common import traced


def run(state: dict) -> dict:
    """TODO (lead): extract context (age band, lab flags, notes) from REDACTED inputs only."""
    trace: list = []
    with traced(trace, "clinical_notes", 2, "redacted context") as t:
        t["output_summary"] = "context extracted (stub)"
    return {"patient_context": state.get("patient_context", {}), "trace": trace}
