"""Output guardrails: every finding cited, no dosing language, disclaimer attached."""
import re

DISCLAIMER_EN = "Decision support only. Not a diagnosis. Please consult a qualified clinician."
DISCLAIMER_BN = "এটি শুধুমাত্র চিকিৎসকের সিদ্ধান্ত-সহায়তা, রোগ নির্ণয় নয়। অনুগ্রহ করে চিকিৎসকের পরামর্শ নিন।"
INSUFFICIENT_EVIDENCE_EN = "Insufficient evidence — consult a clinician."
INSUFFICIENT_EVIDENCE_BN = "পর্যাপ্ত প্রমাণ নেই — অনুগ্রহ করে চিকিৎসকের পরামর্শ নিন।"

# English patterns + a few Bangla keywords. Extend with clinician review; this list is a starting point.
_DOSING_PATTERNS = [
    r"\b(take|taking|increase|decrease|reduce|double|halve|skip|stop|discontinue|start|switch)\b[^.]{0,40}\b(dose|mg|tablet|tablets|medicine|medication|drug)\b",
    r"\b\d+(\.\d+)?\s?(mg|mcg|µg|g|ml|iu)\b",
    r"ওষুধ\s*(বন্ধ|শুরু)",
    r"ডোজ\s*(বাড়ান|কমান|বদলান)",
    r"(বন্ধ|শুরু)\s*করুন",
]
_DOSING_RE = [re.compile(p, re.IGNORECASE) for p in _DOSING_PATTERNS]


def contains_dosing_language(text: str) -> bool:
    return any(rx.search(text or "") for rx in _DOSING_RE)


def findings_missing_evidence(findings: list[dict]) -> list[int]:
    """Indexes of findings that have a severity (not 'unknown') but no evidence."""
    return [i for i, f in enumerate(findings)
            if f.get("severity") != "unknown" and not f.get("evidence")]


def check_output(*, summary_text: str, findings: list[dict]) -> list[str]:
    """Return a list of violations (empty list = passes)."""
    problems: list[str] = []
    if contains_dosing_language(summary_text):
        problems.append("dosing_language")
    missing = findings_missing_evidence(findings)
    if missing:
        problems.append(f"missing_evidence:{missing}")
    return problems
