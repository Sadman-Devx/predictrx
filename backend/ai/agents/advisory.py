"""Advisory agent (step 4).

Writes the doctor summary (EN + BN) and the plain-Bangla patient card FROM THE FINDINGS ONLY.

  * Default path is a deterministic template: every sentence maps to a field of a finding, a gap or an entered
    lab flag. No new medical fact can appear, and no dosing, strengths or lab values are printed.
  * Optional (ADVISORY_USE_LLM=true): an LLM may re-phrase the doctor_en / patient_card_bn BODY. The result is
    accepted only if it keeps every drug name and every source number (#id), has no dosing language and makes no
    "safe" claim; otherwise the template stays. The disclaimer is appended by code, never by the model.
  * Final guard: the same dosing check the runner uses. If anything trips it, the detailed text is rebuilt without
    free text, and as a last resort replaced by the insufficient-evidence text.

Verification status and confidence are NOT written into the text: the Verifier runs after this step and may change
the status; the UI shows both from the finding rows.
"""
import logging
import re

from ..config import setting
from ..guardrails.output_checks import (DISCLAIMER_BN, DISCLAIMER_EN, INSUFFICIENT_EVIDENCE_BN,
                                        INSUFFICIENT_EVIDENCE_EN, contains_dosing_language)
from ..llm.router import complete
from .common import ellipsize, med_label, safe_label, traced

logger = logging.getLogger(__name__)

SEV_BN = {"major": "মারাত্মক", "moderate": "মাঝারি", "minor": "সামান্য", "unknown": "অজানা"}
SOURCE_NAMES = {"ddinter": "DDInter 2.0", "openfda_label": "openFDA label"}
FLAG_BN = {"high": "বেশি", "low": "কম"}
KNOWN = ("major", "moderate", "minor")
MAX_LISTED = 10
RATIONALE_CHARS = 400

_SAFE_CLAIM_EN = re.compile(r"\b(is|are|be|considered|deemed|totally|completely)\s+(safe|harmless)\b", re.IGNORECASE)


# ------------------------------------------------------------------------------------------------ grouping
def _sev(f: dict) -> str:
    return f.get("severity") if f.get("severity") in ("major", "moderate", "minor", "unknown") else "unknown"


def _groups(findings: list):
    flagged = sorted((f for f in findings if _sev(f) in KNOWN),
                     key=lambda f: (KNOWN.index(_sev(f)), f.get("drug_a", ""), f.get("drug_b", "")))
    label_only = [f for f in findings if _sev(f) == "unknown" and f.get("evidence")]
    no_evidence = [f for f in findings if _sev(f) == "unknown" and not f.get("evidence")]
    return flagged, label_only, no_evidence


def _pair(f: dict) -> str:
    return f"{f.get('drug_a', '?')} + {f.get('drug_b', '?')}"


def _sources(evidence: list, lang: str) -> str:
    out = []
    for e in evidence or []:
        name = SOURCE_NAMES.get(e.get("source"), str(e.get("source") or "source"))
        if e.get("type") == "interaction":
            out.append(f"{name} {'রেকর্ড' if lang == 'bn' else 'record'} #{e.get('id')}")
        else:
            out.append(f"{name} {'অনুচ্ছেদ' if lang == 'bn' else 'passage'} #{e.get('id')}")
    return "; ".join(out)


def _listed(items: list, limit: int = MAX_LISTED) -> list:
    return items[:limit]


def _outside_labs(context: dict) -> list:
    return [lab for lab in context.get("lab_flags") or [] if lab.get("flag") in ("high", "low")]


# ------------------------------------------------------------------------------------------------ doctor EN
def _doctor_en_body(findings, gaps, context, n_drugs, *, detail: bool) -> str:
    flagged, label_only, no_evidence = _groups(findings)
    c = {k: sum(1 for f in findings if _sev(f) == k) for k in ("major", "moderate", "minor", "unknown")}
    lines = [
        f"Interaction review: {n_drugs} drugs, {len(findings)} pairs checked.",
        f"Severity counts: major {c['major']}, moderate {c['moderate']}, minor {c['minor']}, "
        f"unknown or no evidence {c['unknown']}.",
    ]
    if flagged:
        lines.append("Findings with a source:")
        for f in flagged:
            line = f"- {_sev(f).upper()}: {_pair(f)}."
            if detail and f.get("rationale"):
                line += f" {ellipsize(f['rationale'], RATIONALE_CHARS)}"
            lines.append(f"{line} Sources: {_sources(f.get('evidence'), 'en')}.")
    if label_only:
        lines.append("Label passages naming both drugs, no severity assigned:")
        for f in _listed(label_only):
            lines.append(f"- {_pair(f)}. Sources: {_sources(f.get('evidence'), 'en')}.")
    if no_evidence:
        names = "; ".join(_pair(f) for f in _listed(no_evidence))
        more = f", and {len(no_evidence) - MAX_LISTED} more" if len(no_evidence) > MAX_LISTED else ""
        lines.append(f"No interaction record found for {len(no_evidence)} pair(s): {names}{more}.")
    if gaps:
        lines.append("Not resolved, therefore not checked (select the generic name manually): "
                     + ", ".join(med_label(g) for g in gaps) + ".")
    ctx = []
    if context.get("age_band"):
        ctx.append(f"age band {context['age_band']}")
    outside = _outside_labs(context)
    if outside:
        ctx.append("labs outside the entered reference range: "
                   + ", ".join(f"{safe_label(lab['test_name'])} ({lab['flag']})" for lab in _listed(outside)))
    if ctx:
        lines.append("Entered data: " + "; ".join(ctx) + ".")
    if detail and context.get("notes_conditions"):
        lines.append("Conditions written in the notes: " + ", ".join(context["notes_conditions"]) + ".")
    lines.append("No record does not mean a combination is safe.")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ doctor BN
def _doctor_bn_body(findings, gaps, context, n_drugs) -> str:
    flagged, label_only, no_evidence = _groups(findings)
    c = {k: sum(1 for f in findings if _sev(f) == k) for k in ("major", "moderate", "minor", "unknown")}
    lines = [
        f"ওষুধের মিথস্ক্রিয়া পর্যালোচনা: {n_drugs} টি ওষুধ, {len(findings)} টি জোড়া যাচাই করা হয়েছে।",
        f"তীব্রতা: মারাত্মক {c['major']}, মাঝারি {c['moderate']}, সামান্য {c['minor']}, "
        f"অজানা বা প্রমাণ নেই {c['unknown']}।",
    ]
    if flagged:
        lines.append("সূত্রসহ ফলাফল:")
        for f in flagged:
            lines.append(f"- [{SEV_BN[_sev(f)]}] {_pair(f)} — সূত্র: {_sources(f.get('evidence'), 'bn')}।")
    if label_only:
        lines.append("লেবেলে দুটি ওষুধেরই উল্লেখ আছে, তবে তীব্রতা নির্ধারিত হয়নি:")
        for f in _listed(label_only):
            lines.append(f"- {_pair(f)} — সূত্র: {_sources(f.get('evidence'), 'bn')}।")
    if no_evidence:
        names = "; ".join(_pair(f) for f in _listed(no_evidence))
        more = f" এবং আরও {len(no_evidence) - MAX_LISTED} টি" if len(no_evidence) > MAX_LISTED else ""
        lines.append(f"{len(no_evidence)} টি জোড়ার জন্য মিথস্ক্রিয়ার কোনো রেকর্ড পাওয়া যায়নি: {names}{more}।")
    if gaps:
        lines.append("নাম চেনা যায়নি, তাই যাচাই হয়নি (জেনেরিক নাম নিজে নির্বাচন করুন): "
                     + ", ".join(med_label(g) for g in gaps) + "।")
    ctx = []
    if context.get("age_band"):
        ctx.append(f"বয়সের গণ্ডি {context['age_band']}")
    outside = _outside_labs(context)
    if outside:
        ctx.append("ল্যাবের মান নির্ধারিত সীমার বাইরে: "
                   + ", ".join(f"{safe_label(lab['test_name'])} ({FLAG_BN[lab['flag']]})" for lab in _listed(outside)))
    if ctx:
        lines.append("প্রবেশ করানো তথ্য: " + "; ".join(ctx) + "।")
    lines.append("রেকর্ড না থাকা মানে সংমিশ্রণটি নিরাপদ, তা নয়।")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ patient card
def _patient_card_body(findings, gaps) -> str:
    flagged, _, _ = _groups(findings)
    strong = [f for f in flagged if _sev(f) in ("major", "moderate")]
    minor = [f for f in flagged if _sev(f) == "minor"]
    lines = ["আপনার ওষুধের তালিকা পর্যালোচনা করা হয়েছে।"]
    for group, heading in ((strong, "এই ওষুধগুলো একসাথে চললে বিশেষ নজর রাখা দরকার হতে পারে:"),
                           (minor, "এই ওষুধগুলোর ক্ষেত্রে সামান্য সতর্কতা আছে:")):
        if group:
            lines.append(heading)
            lines.extend(f"- {f.get('drug_a', '?')} ও {f.get('drug_b', '?')}" for f in group[:6])
            if len(group) > 6:
                lines.append(f"- আরও {len(group) - 6} টি জোড়া আছে")
    if flagged:
        lines.append("এ বিষয়ে আপনার চিকিৎসক বা ফার্মাসিস্টের সঙ্গে কথা বলুন।")
    else:
        lines.append("এই তালিকার জন্য কোনো সতর্কতার রেকর্ড পাওয়া যায়নি। "
                     "তবে রেকর্ড না থাকা মানে ওষুধগুলো একসাথে নিরাপদ, তা নয়।")
    if gaps:
        lines.append("কিছু ওষুধের নাম চেনা যায়নি, তাই সেগুলো দেখা হয়নি।")
    lines.append("কোনো ওষুধ পরিবর্তন করার আগে অনুগ্রহ করে আপনার চিকিৎসকের সঙ্গে কথা বলুন।")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ optional LLM polish
def _polish_problem(text: str, base: str, findings: list):
    if not text:
        return "empty"
    if len(text) > 2 * len(base) + 300:
        return "too_long"
    if contains_dosing_language(text):
        return "dosing_language"
    lowered = text.lower()
    flagged, _, _ = _groups(findings)
    for f in flagged:
        for name in (f.get("drug_a", ""), f.get("drug_b", "")):
            if name and name.lower() not in lowered:
                return "drug_name_missing"
    if not set(re.findall(r"#\d+", base)) <= set(re.findall(r"#\d+", text)):
        return "source_missing"
    if _SAFE_CLAIM_EN.search(text) or text.count("নিরাপদ") > base.count("নিরাপদ"):
        return "safety_claim"
    return None


def _polish(target: str, base: str, findings: list, *, language: str, audience: str, tool_calls: list) -> str:
    if not setting("ADVISORY_USE_LLM", False):
        return base
    local = bool(setting("ADVISORY_LLM_LOCAL", False))
    system = ("You improve the readability of a drug-interaction summary. You must not add, remove or change any "
              "fact. No dosing. No instruction to start, stop or change any medicine. Keep every drug name exactly "
              "as written in English letters and keep every '#number' source reference. Output only the text.")
    prompt = f"Rewrite the text below in {language} for {audience}. Keep the same facts.\n\nTEXT:\n{base}"
    kw = {"system": system} if local else {"system": system, "max_tokens": 900}
    try:
        raw = complete(prompt, sensitive=local, **kw)  # findings hold drug names only: no patient data goes out
    except Exception:  # noqa: BLE001 — optional enrichment: any model/network failure keeps the template
        logger.warning("advisory LLM polish failed for %s; keeping the template", target, exc_info=True)
        tool_calls.append({"tool": "llm.polish", "target": target, "accepted": False, "reason": "call_failed"})
        return base
    text = (raw or "").strip()
    problem = _polish_problem(text, base, findings)
    tool_calls.append({"tool": "llm.polish", "target": target, "accepted": problem is None,
                       "reason": problem or "", "local": local})
    return base if problem else text


# ------------------------------------------------------------------------------------------------ node
def run(state: dict) -> dict:
    trace: list = []
    findings = list(state.get("findings") or [])
    gaps = list(state.get("gaps") or [])
    context = state.get("patient_context") or {}
    n_drugs = len(state.get("resolved_drugs") or [])
    with traced(trace, "advisory", 4, f"{len(findings)} findings") as t:
        en = _doctor_en_body(findings, gaps, context, n_drugs, detail=True)
        bn = _doctor_bn_body(findings, gaps, context, n_drugs)
        card = _patient_card_body(findings, gaps)

        en = _polish("doctor_en", en, findings, language="English", audience="a busy clinician (keep it concise)",
                     tool_calls=t["tool_calls"])
        card = _polish("patient_card_bn", card, findings, language="plain, simple Bangla",
                       audience="a patient or caregiver (short sentences, no jargon)", tool_calls=t["tool_calls"])

        doctor_en = f"{en}\n\n{DISCLAIMER_EN}"
        doctor_bn = f"{bn}\n\n{DISCLAIMER_BN}"
        patient_card = f"{card}\n\n{DISCLAIMER_BN}"

        guard = "passed"
        if contains_dosing_language(" ".join((doctor_en, doctor_bn, patient_card))):
            guard = "rebuilt_without_free_text"
            doctor_en = f"{_doctor_en_body(findings, gaps, context, n_drugs, detail=False)}\n\n{DISCLAIMER_EN}"
            doctor_bn = f"{_doctor_bn_body(findings, gaps, context, n_drugs)}\n\n{DISCLAIMER_BN}"
            patient_card = f"{_patient_card_body(findings, gaps)}\n\n{DISCLAIMER_BN}"
            if contains_dosing_language(" ".join((doctor_en, doctor_bn, patient_card))):
                guard = "replaced_insufficient_evidence"
                doctor_en = f"{INSUFFICIENT_EVIDENCE_EN}\n\n{DISCLAIMER_EN}"
                doctor_bn = f"{INSUFFICIENT_EVIDENCE_BN}\n\n{DISCLAIMER_BN}"
                patient_card = f"{INSUFFICIENT_EVIDENCE_BN}\n\n{DISCLAIMER_BN}"

        summaries = {"doctor_en": doctor_en, "doctor_bn": doctor_bn, "patient_card_bn": patient_card,
                     "disclaimer_en": DISCLAIMER_EN, "disclaimer_bn": DISCLAIMER_BN}
        polished = [c for c in t["tool_calls"] if c.get("accepted")]
        t["output_summary"] = (f"summaries drafted from {len(findings)} findings; "
                               f"llm_polish_accepted={len(polished)}; dosing_guard={guard}")
    return {"summaries": summaries, "trace": trace}