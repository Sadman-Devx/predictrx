"""PII redaction. Runs BEFORE any text is sent to a cloud LLM (ai/llm/router.py enforces it again at the door).

What it catches (rule-based, deterministic, no model):
  EMAIL    e-mail addresses
  PHONE    Bangladesh mobile numbers, also written with Bangla digits
  ID       long digit runs (NID/birth-certificate style, Bangla digits too) and labelled IDs (NID / passport ...)
  NAME     a name after "Name:" / "নাম:", and the name after an honorific (Mr, Mrs, Ms, Dr, Md, Mst, Prof)
  ADDRESS  text after "Address:" / "ঠিকানা:", and "House 12", "Road 5", "Block B", "Flat 3" style parts
  DOB      a date or year after "DOB" / "date of birth" / "born"

Limits (be honest in the pitch): this is pattern based. A personal name or address written WITHOUT a label or
honorific is not reliably caught. Keep such free text on the local Ollama path, or add an NER step, before claiming
stronger protection. Drug names, labs and clinical words are left untouched so the agents still have context.

Properties: the output of redact() is stable (redacting it again changes nothing and counts nothing), so the
double-redaction in apps/analysis/services.py does not inflate `redaction_counts`.
"""
import re
from dataclasses import dataclass, field

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")  # 1:1, so spans found on the translated text fit the original

# Order matters: labelled patterns first, then the generic ones. (label, compiled pattern). A named group `v`
# means "replace only this group" (the label stays readable: "Name: [NAME]").
_PATTERNS = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("NAME", re.compile(
        r"(?<!drug )(?<!Drug )(?<!medicine )(?<!Medicine )(?<!brand )(?<!Brand )(?<!generic )(?<!Generic )"
        r"\b(?i:patient\s+)?(?i:name)\s*[:\-]\s*(?P<v>(?:[A-Z][A-Za-z]*\.?[ \t]+){0,3}[A-Z][A-Za-z]*)")),
    ("NAME", re.compile(r"নাম\s*[:\-]\s*(?P<v>[\u0980-\u09FF]+(?:[ \t]+[\u0980-\u09FF]+){0,3})")),
    ("NAME", re.compile(
        r"\b(?i:mr|mrs|ms|miss|dr|md|mst|prof)\.?\s+(?P<v>[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,2})")),
    ("ADDRESS", re.compile(r"(?i)\b(?:address|addr)\s*[:\-]\s*(?P<v>(?!\s|\[)[^\n]{3,120})")),
    ("ADDRESS", re.compile(r"ঠিকানা\s*[:\-]\s*(?P<v>(?!\s|\[)[^\n]{3,120})")),
    ("ADDRESS", re.compile(r"(?i)\b(?:house|flat|road|block|sector)\s*(?:no\.?\s*)?#?\d+[A-Za-z]?\b")),
    ("DOB", re.compile(
        r"(?i)\b(?:dob|d\.o\.b\.?|date of birth|born(?: on)?)\s*[:\-]?\s*"
        r"(?P<v>\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4})\b")),
    # Bangladesh mobile numbers: +8801XXXXXXXXX, 8801XXXXXXXXX, 01XXXXXXXXX (also with dashes/spaces)
    ("PHONE", re.compile(r"(?<!\d)(?:\+?88[\s-]?)?01[3-9](?:[\s-]?\d){8}(?!\d)")),
    ("ID", re.compile(
        r"(?i)\b(?:nid|national id|birth certificate|bcn|passport)(?:\s*(?:no|number|#))?\.?\s*[:\-]?\s*"
        r"(?P<v>(?=[A-Za-z0-9\-]*\d{5})[A-Za-z0-9\-]{6,20})")),
    # ID-like digit runs (NID 10/13/17 digits, etc.), Bangla digits are normalised before matching
    ("ID", re.compile(r"(?<!\d)\d{10,17}(?!\d)")),
]


@dataclass
class RedactionResult:
    text: str
    counts: dict = field(default_factory=dict)


def _replace(text: str, label: str, pattern: re.Pattern) -> tuple[str, int]:
    normalised = text.translate(_BN_DIGITS)
    pieces, last, n = [], 0, 0
    for m in pattern.finditer(normalised):
        start, end = m.span("v") if "v" in pattern.groupindex else m.span()
        if end <= start or start < last:
            continue
        pieces.append(text[last:start])
        pieces.append(f"[{label}]")
        last, n = end, n + 1
    if not n:
        return text, 0
    pieces.append(text[last:])
    return "".join(pieces), n


def redact(text: str) -> RedactionResult:
    counts: dict[str, int] = {}
    text = text or ""
    for label, pattern in _PATTERNS:
        text, n = _replace(text, label, pattern)
        if n:
            counts[label] = counts.get(label, 0) + n
    return RedactionResult(text=text, counts=counts)


def contains_pii(text: str) -> bool:
    """True when redact() would change the text."""
    return bool(redact(text).counts)