from .common import traced


def run(state: dict) -> dict:
    """TODO (lead): call the resolve_brand MCP tool for every medication. Unresolved items stay as explicit gaps."""
    trace: list = []
    with traced(trace, "resolver", 1, f"{len(state.get('medications', []))} medications") as t:
        resolved, gaps = [], []
        for med in state.get("medications", []):
            gaps.append(med)  # stub: nothing resolved yet
        t["output_summary"] = f"resolved={len(resolved)} gaps={len(gaps)} (stub)"
    return {"resolved_drugs": resolved, "gaps": gaps, "trace": trace}
