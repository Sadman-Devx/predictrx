from ..guardrails.output_checks import DISCLAIMER_BN, DISCLAIMER_EN
from .common import traced


def run(state: dict) -> dict:
    """TODO (lead): write doctor summary + plain-Bangla patient card FROM THE FINDINGS ONLY (no new facts, no dosing)."""
    trace: list = []
    with traced(trace, "advisory", 4, f"{len(state.get('findings', []))} findings") as t:
        summaries = {"doctor_en": "", "doctor_bn": "", "patient_card_bn": "",
                     "disclaimer_en": DISCLAIMER_EN, "disclaimer_bn": DISCLAIMER_BN}
        t["output_summary"] = "summaries drafted (stub)"
    return {"summaries": summaries, "trace": trace}
