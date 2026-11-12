"""Name normalisation helpers for drug lookup (kept in sync with data/pipeline/clean.py — see the parity test)."""
import re

SALT_WORDS = {
    "hydrochloride", "hcl", "sodium", "potassium", "calcium", "magnesium", "sulfate", "sulphate", "mesylate",
    "maleate", "tartrate", "besylate", "succinate", "phosphate", "acetate", "citrate", "hydrobromide", "bromide",
    "fumarate", "nitrate", "carbonate", "dihydrate", "monohydrate", "anhydrous", "hemihydrate",
}
# words that describe the product form, not the drug
FORM_WORDS = {
    "tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules", "syrup", "syp", "susp", "suspension",
    "inj", "injection", "drop", "drops", "cream", "ointment", "gel", "sachet", "suppository", "oral", "iv",
}
_STRENGTH_RE = re.compile(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>mg|mcg|µg|ug|g|ml|iu|%)(?![a-z])", re.IGNORECASE)
_TRAILING_NUMBER_RE = re.compile(r"\s(?P<num>\d+(?:\.\d+)?)$")


def key(text: str) -> str:
    """Lookup key: lower-case, collapsed whitespace. Parentheses are KEPT ("diclofenac (topical)" is its own drug)."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def normalize_name(name: str) -> str:
    name = re.sub(r"\(.*?\)", " ", name.lower())
    name = re.sub(r"[^a-z0-9 ]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def strip_salt(name: str) -> str:
    """'warfarin sodium' -> 'warfarin'. Falls back to the normalised name if everything would be stripped."""
    norm = normalize_name(name)
    kept = [t for t in norm.split() if t not in SALT_WORDS]
    return " ".join(kept) or norm


def parse_input(raw: str) -> dict:
    """Split what a clinician typed into {text, strength}. 'Napa 500mg tab' -> text='napa', strength='500mg'."""
    s = key(raw)
    strength = None
    m = _STRENGTH_RE.search(s)
    if m:
        strength = f"{m.group('num').replace(',', '.')}{m.group('unit').lower()}"
        s = (s[:m.start()] + " " + s[m.end():]).strip()
    else:
        m = _TRAILING_NUMBER_RE.search(s)
        if m:  # "napa 500" -> bare number, unit unknown
            strength = m.group("num")
            s = s[:m.start()].strip()
    tokens = [t for t in key(s).split(" ") if t and t not in FORM_WORDS]
    return {"text": " ".join(tokens), "strength": strength}