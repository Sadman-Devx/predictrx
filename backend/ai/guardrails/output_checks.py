"""Output guardrails: every finding cited, no dosing language, no "safe" claim, disclaimer attached.

`check_output(summary_text=..., findings=...)` keeps its Day 1 meaning (dosing + missing evidence) and is still what
apps/analysis/runner.py calls on the text it is about to store. Pass `summaries={...}` as well to also check the
"safe" claim and the disclaimers (the Verifier does).
"""
import re

DISCLAIMER_EN = "Decision support only. Not a diagnosis. Please consult a qualified clinician."
DISCLAIMER_BN = "এটি শুধুমাত্র চিকিৎসকের সিদ্ধান্ত-সহায়তা, রোগ নির্ণয় নয়। অনুগ্রহ করে চিকিৎসকের পরামর্শ নিন।"
INSUFFICIENT_EVIDENCE_EN = "Insufficient evidence — consult a clinician."
INSUFFICIENT_EVIDENCE_BN = "পর্যাপ্ত প্রমাণ নেই — অনুগ্রহ করে চিকিৎসকের পরামর্শ নিন।"

SUMMARY_KEYS = ("doctor_en", "doctor_bn", "patient_card_bn")
DISCLAIMER_FOR = {"doctor_en": DISCLAIMER_EN, "doctor_bn": DISCLAIMER_BN, "patient_card_bn": DISCLAIMER_BN}
INSUFFICIENT_FOR = {"doctor_en": INSUFFICIENT_EVIDENCE_EN, "doctor_bn": INSUFFICIENT_EVIDENCE_BN,
                    "patient_card_bn": INSUFFICIENT_EVIDENCE_BN}

# English patterns + a few Bangla keywords. Extend with clinician review; this list is a starting point.
_DOSING_PATTERNS = [
    r"\b(take|taking|increase|decrease|reduce|double|halve|skip|stop|discontinue|start|switch)\b[^.]{0,40}\b(dose|mg|tablet|tablets|medicine|medication|drug)\b",
    r"\b\d+(\.\d+)?\s?(mg|mcg|µg|g|ml|iu)\b",
    r"ওষুধ\s*(বন্ধ|শুরু)",
    r"ডোজ\s*(বাড়ান|কমান|বদলান)",
    r"(বন্ধ|শুরু)\s*করুন",
]
_DOSING_RE = [re.compile(p, re.IGNORECASE) for p in _DOSING_PATTERNS]

# "safe" is only allowed inside a negation ("this does not mean the combination is safe").
_SAFE_EN = re.compile(r"\b(safe|harmless)\b", re.IGNORECASE)
_NEGATION_EN = re.compile(r"\b(not|no|never|cannot|can't|isn't|aren't)\b", re.IGNORECASE)
_NEGATION_BN = ("না", "নয়", "নেই")
_SENTENCES = re.compile(r"(?<=[.!?।])\s+|\n+")


def contains_dosing_language(text: str) -> bool:
    return any(rx.search(text or "") for rx in _DOSING_RE)


def claims_safety(text: str) -> bool:
    """True when a sentence calls a combination safe/harmless without a negation. Absence of data is not safety."""
    for sentence in _SENTENCES.split(text or ""):
        if _SAFE_EN.search(sentence) and not _NEGATION_EN.search(sentence):
            return True
        if "নিরাপদ" in sentence and not any(word in sentence for word in _NEGATION_BN):
            return True
    return False


def missing_disclaimers(summaries: dict) -> list[str]:
    """Summary keys that have text but not their disclaimer."""
    return [k for k in SUMMARY_KEYS
            if isinstance(summaries.get(k), str) and summaries[k].strip() and DISCLAIMER_FOR[k] not in summaries[k]]


def summary_violations(summaries: dict) -> list[str]:
    """Violations in the summaries other than dosing language (that one is checked on the joined text)."""
    text = " ".join(str(summaries.get(k) or "") for k in SUMMARY_KEYS)
    problems = ["safety_claim"] if claims_safety(text) else []
    problems += [f"disclaimer_missing:{k}" for k in missing_disclaimers(summaries)]
    return problems


def findings_missing_evidence(findings: list[dict]) -> list[int]:
    """Indexes of findings that have a severity (not 'unknown') but no evidence."""
    return [i for i, f in enumerate(findings)
            if f.get("severity") != "unknown" and not f.get("evidence")]


def check_output(*, summary_text: str, findings: list[dict], summaries: dict | None = None) -> list[str]:
    """Return a list of violations (empty list = passes)."""
    problems: list[str] = []
    if contains_dosing_language(summary_text):
        problems.append("dosing_language")
    missing = findings_missing_evidence(findings)
    if missing:
        problems.append(f"missing_evidence:{missing}")
    if summaries is not None:
        problems.extend(summary_violations(summaries))
    return problems