"""PII redaction. Runs BEFORE any text is sent to a cloud LLM.

Limits (be honest in the pitch): this is regex-based. It catches emails, phone numbers and long ID-like digit
runs. It does NOT reliably catch personal names or addresses in free text. Add an NER step (or keep such text on
the local Ollama path) before claiming stronger protection.
"""
import re
from dataclasses import dataclass, field

_PATTERNS = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # Bangladesh mobile numbers: +8801XXXXXXXXX, 8801XXXXXXXXX, 01XXXXXXXXX (also with dashes/spaces)
    ("PHONE", re.compile(r"(?<!\d)(?:\+?88[\s-]?)?01[3-9](?:[\s-]?\d){8}(?!\d)")),
    # ID-like digit runs (NID 10/13/17 digits, etc.), also Bangla digits
    ("ID", re.compile(r"(?<![\d০-৯])[\d০-৯]{10,17}(?![\d০-৯])")),
]


@dataclass
class RedactionResult:
    text: str
    counts: dict = field(default_factory=dict)


def redact(text: str) -> RedactionResult:
    counts: dict[str, int] = {}
    for label, pattern in _PATTERNS:
        text, n = pattern.subn(f"[{label}]", text)
        if n:
            counts[label] = counts.get(label, 0) + n
    return RedactionResult(text=text, counts=counts)
