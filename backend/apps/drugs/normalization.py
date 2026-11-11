"""Text normalization for brand/generic names typed or scanned from prescriptions."""
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

_STRENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mg|mcg|µg|g|ml|iu)?\b")
_FORM_RE = re.compile(
    r"\b(?:tab|tabs|tablet|tablets|cap|caps|capsule|capsules|syp|syrup|inj|injection)\b\.?"
)


def normalize_name(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw or "").lower().strip()
    text = re.sub(r"[^\w\s.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text


def _clean_number(value: str) -> str:
    # "500.0" -> "500", "500" -> "500"
    return value.rstrip("0").rstrip(".") if "." in value else value


def strength_number(strength: Optional[str]) -> Optional[str]:
    """'500 mg' -> '500'. Unit assume kori na; shudhu number compare kori."""
    if not strength:
        return None
    m = _STRENGTH_RE.search(normalize_name(strength))
    return _clean_number(m.group(1)) if m else None


@dataclass(frozen=True)
class ParsedInput:
    name: str
    strength_num: Optional[str]


def parse_input(raw: str) -> ParsedInput:
    """'Tab. Napa 500mg' -> name='napa', strength_num='500'."""
    text = normalize_name(raw)
    m = _STRENGTH_RE.search(text)
    strength_num = _clean_number(m.group(1)) if m else None
    if m:
        text = f"{text[:m.start()]} {text[m.end():]}"
    text = _FORM_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return ParsedInput(name=text, strength_num=strength_num)