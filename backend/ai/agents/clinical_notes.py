"""Clinical Notes agent (step 2).

Works only on the REDACTED snapshot. Deterministic by default:
  * age band / sex / weight pass through,
  * each lab is compared with the reference range the clinician ENTERED (no thresholds of our own);
    no range or no value -> flagged as such, never guessed,
  * labs are grouped into renal / hepatic / coagulation / electrolyte for the doctor summary.

Optional (CLINICAL_NOTES_USE_LLM=true + LOCAL_LLM_MODEL): the LOCAL model lists condition phrases found in the
notes. Every phrase must be a verbatim substring of the notes or it is dropped, so the model cannot add facts.
Raw note text is not passed on: later agents get lab flags, a note count and the validated phrases only.
"""
import json
import logging
import re

from ..config import setting
from ..guardrails.pii import redact
from ..llm.router import local_complete
from .common import traced

logger = logging.getLogger(__name__)

MAX_NOTES_CHARS = 4000
MAX_PHRASES = 8

_CATEGORIES = {
    "renal": ("creatinine", "egfr", "gfr", "urea", "bun", "cystatin"),
    "hepatic": ("alt", "sgpt", "ast", "sgot", "bilirubin", "alkaline phosphatase", "alp", "ggt", "albumin"),
    "coagulation": ("inr", "prothrombin", "aptt", "ptt"),
    "electrolyte": ("potassium", "sodium", "magnesium", "calcium"),
}
_NUM = r"-?\d+(?:\.\d+)?"
_BETWEEN = re.compile(rf"^\s*({_NUM})\s*(?:-|to)\s*({_NUM})", re.IGNORECASE)
_UPPER = re.compile(rf"^\s*(?:<=|<)\s*({_NUM})")
_LOWER = re.compile(rf"^\s*(?:>=|>)\s*({_NUM})")


def _to_float(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_range(text: str):
    """'0.6-1.2' -> (0.6, 1.2); '<5' -> (None, 5.0); '>=60' -> (60.0, None); anything else -> None."""
    t = (text or "").strip().replace("–", "-").replace("—", "-").replace("≤", "<=").replace("≥", ">=")
    m = _BETWEEN.match(t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (lo, hi) if lo <= hi else None
    m = _UPPER.match(t)
    if m:
        return (None, float(m.group(1)))
    m = _LOWER.match(t)
    if m:
        return (float(m.group(1)), None)
    return None


def lab_flag(value, ref_range: str) -> str:
    v = _to_float(value)
    if v is None:
        return "no_value"
    bounds = parse_range(ref_range)
    if bounds is None:
        return "no_reference_range"
    lo, hi = bounds
    if lo is not None and v < lo:
        return "low"
    if hi is not None and v > hi:
        return "high"
    return "within_range"


def lab_category(test_name: str) -> str:
    haystack = f" {' '.join(re.findall(r'[a-z0-9]+', (test_name or '').lower()))} "
    for category, words in _CATEGORIES.items():
        if any(f" {w} " in haystack for w in words):
            return category
    return "other"


def _validated_phrases(raw: str, source_text: str) -> list:
    match = re.search(r"\[.*\]", raw or "", re.DOTALL)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except ValueError:
        return []
    lowered, out = source_text.lower(), []
    for item in items if isinstance(items, list) else []:
        phrase = " ".join(str(item).split())
        if 3 <= len(phrase) <= 60 and phrase.lower() in lowered and phrase not in out:
            out.append(phrase)
    return out[:MAX_PHRASES]


def _extract_conditions(notes: list):
    if not notes:
        return [], "no_notes"
    if not setting("CLINICAL_NOTES_USE_LLM", False):
        return [], "llm_off"
    if not setting("LOCAL_LLM_MODEL", ""):
        return [], "llm_not_configured"
    text = redact("\n".join(notes)).text[:MAX_NOTES_CHARS]
    prompt = (
        "From the clinical notes below, list the medical conditions or allergies that are written in them.\n"
        "Return ONLY a JSON array of short strings. Copy each phrase exactly as written in the notes. "
        "Do not add anything that is not written there. Do not give advice.\n\nNOTES:\n" + text
    )
    try:
        raw = local_complete(prompt, system="You extract exact phrases from text. You never add information.")
    except Exception:  # noqa: BLE001 — optional enrichment: any local-model failure must not stop the run
        logger.warning("clinical notes extraction failed; continuing without it", exc_info=True)
        return [], "llm_failed"
    return _validated_phrases(raw, text), "llm_validated"


def run(state: dict) -> dict:
    trace: list = []
    ctx = state.get("patient_context") or {}
    labs = ctx.get("labs") or []
    notes = [n for n in (ctx.get("notes") or []) if isinstance(n, str) and n.strip()]
    with traced(trace, "clinical_notes", 2, f"redacted context: {len(labs)} labs, {len(notes)} notes") as t:
        lab_flags = []
        for lab in labs:
            name = str(lab.get("test_name") or "").strip()
            if not name:
                continue
            lab_flags.append({
                "test_name": name,
                "value": lab.get("value"),
                "unit": lab.get("unit") or "",
                "category": lab_category(name),
                "flag": lab_flag(lab.get("value"), lab.get("ref_range") or ""),
            })
        outside = [f for f in lab_flags if f["flag"] in ("high", "low")]
        conditions, notes_status = _extract_conditions(notes)

        context = {
            "age_band": ctx.get("age_band"),
            "sex": ctx.get("sex"),
            "weight_kg": ctx.get("weight_kg"),
            "lab_flags": lab_flags,
            "categories_outside_range": sorted({f["category"] for f in outside if f["category"] != "other"}),
            "notes_count": len(notes),
            "notes_conditions": conditions,
        }
        if notes_status in ("llm_validated", "llm_failed"):
            t["tool_calls"].append({"tool": "local_llm.extract_conditions", "status": notes_status,
                                    "phrases": len(conditions)})
        t["output_summary"] = (
            f"age_band={context['age_band'] or 'n/a'}; labs={len(lab_flags)} outside_entered_range={len(outside)}; "
            f"notes={len(notes)} conditions={len(conditions)} ({notes_status})"
        )
    return {"patient_context": context, "trace": trace}