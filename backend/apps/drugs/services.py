"""Deterministic drug tools — the single source of truth for brand resolution and interaction lookup.

Three plain functions, used by BOTH the REST API (apps/drugs/views.py) and the MCP server (mcp-server/server.py),
so the Verifier agent and the UI can never disagree about what the tables say:

    resolve_brand(brand, strength=None) -> generic + confidence + basis (match_type/source/verified) | unresolved
    lookup_drug(generic_name)           -> basic record + sources                                       | not_found
    check_interaction(drug_a, drug_b)   -> severity/mechanism/management/source                         | no_record

Rules these functions enforce (docs/rule.md):
  * Never guess. Exact match -> fuzzy match above a strict threshold -> otherwise `unresolved`.
  * A fuzzy match is never `verified` and always says so (`match_type == "fuzzy"`): the UI must ask the user.
  * Every confidence value ships with its basis (match_type, source, verified).
  * `no_record` means "no evidence found" — it is NEVER "safe". No status in this module says "safe".

Response shapes are a contract (Verifier + tests depend on them): new keys may be added, existing keys must not
change meaning.
"""
import difflib
import logging
import re
import unicodedata
import uuid

from django.core.cache import cache
from django.db.models import Q

from .models import BrandMapping, Drug, Interaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------------------------
# Tunables (conservative on purpose — a wrong silent match is worse than asking the user)
# ---------------------------------------------------------------------------------------------------------------
MAX_INPUT_LEN = 120
MIN_RESOLVE_CONFIDENCE = 0.60  # below this a match is returned as `unresolved` (reason: low_confidence)
FUZZY_MIN_RATIO = 0.88  # difflib similarity needed before a typo-match is even considered
FUZZY_MIN_LEN = 4  # names shorter than this are never fuzzy-matched (too many false friends)
FUZZY_MARGIN = 0.04  # best fuzzy hit must beat the best hit of a *different* drug by at least this much
FUZZY_CONFIDENCE_CAP = 0.85
CACHE_TTL = 300  # seconds; the data-version key makes reloads visible immediately
SEARCH_MAX_LIMIT = 20

SEVERITY_RANK = {"major": 3, "moderate": 2, "minor": 1, "unknown": 0}
NO_RECORD_NOTE = "No interaction record found. This does not mean the combination is safe."

# ---------------------------------------------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------------------------------------------
_FORM_WORDS = (
    r"(?:tab|tabs|tablet|tablets|cap|caps|capsule|capsules|syr|syrup|susp|suspension|inj|injection|"
    r"drops|cream|oint|ointment|gel|sachet)"
)
_FORM_PREFIX = re.compile(rf"^\s*{_FORM_WORDS}\b[.\s]*", re.IGNORECASE)
_FORM_SUFFIX = re.compile(rf"[\s.]*\b{_FORM_WORDS}\b[.\s]*$", re.IGNORECASE)
# "500", "500mg", "0.5 g", "Napa500" — a number that is not part of a longer number.
_STRENGTH_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(mg|mcg|µg|ug|g|ml|iu|%)?(?![\d])", re.IGNORECASE)
_TO_MG = {"mg": 1.0, "g": 1000.0, "mcg": 0.001, "µg": 0.001, "ug": 0.001}


def _key(text: str) -> str:
    """Lower-case, NFKC, punctuation -> space, whitespace collapsed. 'Napa-500' -> 'napa 500'."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^\w\s%]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_forms(text: str) -> str:
    text = _FORM_PREFIX.sub("", text, count=1)
    return _FORM_SUFFIX.sub("", text, count=1)


def _parse_strength(text: str | None) -> tuple[float, str] | None:
    """First numeric strength in `text` as (value, unit) with the unit normalised ('' when none was written)."""
    if not text:
        return None
    m = _STRENGTH_RE.search(unicodedata.normalize("NFKC", text))
    if not m:
        return None
    unit = (m.group(2) or "").lower()
    value = float(m.group(1))
    if unit in _TO_MG:
        return value * _TO_MG[unit], "mg"
    return value, unit


def _strength_matches(wanted: tuple[float, str] | None, have: str) -> bool:
    """'500' matches '500 mg' (unit omitted = accept); '0.5 g' matches '500 mg'; '650' does not match '500 mg'."""
    have_parsed = _parse_strength(have)
    if wanted is None or have_parsed is None:
        return False
    (w_val, w_unit), (h_val, h_unit) = wanted, have_parsed
    if w_unit and h_unit and w_unit != h_unit:
        return False
    return abs(w_val - h_val) < 1e-9


def _split_input(raw: str, strength_arg: str | None) -> tuple[list[str], tuple[float, str] | None]:
    """-> (candidate name keys to try, strength). The full string is tried first so brands with digits in their
    own name ('Vitamin B12') still match before we strip anything that looks like a strength."""
    cleaned = _strip_forms(_key(raw))
    full_key = cleaned
    strength = _parse_strength(strength_arg)
    m = _STRENGTH_RE.search(cleaned)
    name_key = cleaned
    if m:
        name_key = re.sub(r"\s+", " ", (cleaned[: m.start()] + " " + cleaned[m.end():])).strip()
        strength = strength or _parse_strength(m.group(0))
    candidates = [k for k in dict.fromkeys([full_key, name_key]) if k]
    return candidates, strength


# ---------------------------------------------------------------------------------------------------------------
# Cache (versioned: a data reload or an admin edit makes every cached answer stale at once)
# ---------------------------------------------------------------------------------------------------------------
_VERSION_KEY = "drugs:data_version"


def invalidate_cache() -> None:
    """Call after any bulk load (bulk_create does not fire signals). Admin/ORM saves call it via signals."""
    try:
        cache.set(_VERSION_KEY, uuid.uuid4().hex, None)
    except Exception:  # noqa: BLE001 — a cache outage must never break a clinical lookup
        logger.warning("drug cache invalidation failed", exc_info=True)


def _version() -> str:
    try:
        v = cache.get(_VERSION_KEY)
        if v is None:
            cache.add(_VERSION_KEY, uuid.uuid4().hex, None)
            v = cache.get(_VERSION_KEY)
        return v or "nocache"
    except Exception:  # noqa: BLE001
        return "nocache"


def _cached(name: str, args: tuple, compute):
    """Cache `compute()` under (version, name, args). Cache failures fall through to a live computation."""
    ver = _version()
    if ver == "nocache":
        return compute()
    key = f"drugs:{ver}:{name}:" + uuid.uuid5(uuid.NAMESPACE_URL, "|".join(str(a) for a in args)).hex  # memcached-safe
    try:
        hit = cache.get(key)
    except Exception:  # noqa: BLE001
        return compute()
    if hit is not None:
        return hit
    value = compute()
    try:
        cache.set(key, value, CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass
    return value


# ---------------------------------------------------------------------------------------------------------------
# In-memory name index (brands + generics + aliases), rebuilt when the data version changes
# ---------------------------------------------------------------------------------------------------------------
def _build_index() -> dict:
    drugs = {d.id: d for d in Drug.objects.all()}
    by_key: dict[str, list[dict]] = {}

    def add(entry: dict) -> None:
        by_key.setdefault(entry["key"], []).append(entry)

    for d in drugs.values():
        for name in [d.generic_name, *(d.aliases or [])]:
            if isinstance(name, str) and _key(name):
                add({"kind": "generic", "name": name, "key": _key(name), "drug_id": d.id,
                     "generic": d.generic_name, "strength": "", "dosage_form": "", "source": "drug_table",
                     "source_ref": "", "source_accessed": None, "verified": False, "confidence": 1.0})
    for b in BrandMapping.objects.select_related("drug").all():
        if _key(b.brand_name):
            add({"kind": "brand", "name": b.brand_name, "key": _key(b.brand_name), "drug_id": b.drug_id,
                 "generic": b.drug.generic_name, "strength": b.strength, "dosage_form": b.dosage_form,
                 "source": b.source, "source_ref": b.source_ref,
                 "source_accessed": b.source_accessed.isoformat() if b.source_accessed else None,
                 "verified": b.verified, "confidence": float(b.confidence)})
    return {
        "by_key": by_key,
        "drugs": {i: {"generic": d.generic_name, "aliases": list(d.aliases or [])} for i, d in drugs.items()},
    }


def _index() -> dict:
    return _cached("index", (), _build_index)


def _aliases_of(index: dict, drug_id: int) -> list[str]:
    return index["drugs"].get(drug_id, {}).get("aliases", [])


# ---------------------------------------------------------------------------------------------------------------
# resolve_brand
# ---------------------------------------------------------------------------------------------------------------
def _unresolved(raw: str, reason: str, candidates: list[str] | None = None) -> dict:
    out = {"status": "unresolved", "input": raw, "reason": reason}
    if candidates:
        out["candidates"] = sorted(set(candidates))  # suggestions for the user to pick from — never auto-applied
    return out


def _resolve_entries(raw: str, entries: list[dict], strength, index: dict, *, match_type: str,
                     similarity: float = 1.0) -> dict:
    """Turn the index entries found for one name into a single answer, or an honest `unresolved`."""
    brand_rows = [e for e in entries if e["kind"] == "brand"]
    rows = brand_rows or entries  # a brand mapping is more specific than a bare generic-name hit
    strength_matched = None
    if brand_rows and strength is not None:
        narrowed = [e for e in brand_rows if _strength_matches(strength, e["strength"])]
        strength_matched = bool(narrowed)
        rows = narrowed or brand_rows

    drug_ids = {e["drug_id"] for e in rows}
    if len(drug_ids) > 1:  # same name maps to different drugs: ask, never pick
        return _unresolved(raw, "ambiguous", [e["generic"] for e in rows])

    best = max(rows, key=lambda e: (e["verified"], e["confidence"]))
    confidence = best["confidence"]
    verified = best["verified"]
    if match_type == "fuzzy":
        confidence = min(confidence * similarity, FUZZY_CONFIDENCE_CAP)
        verified = False  # a typo-match is never "verified", whatever the row says
    confidence = round(confidence, 2)
    if confidence < MIN_RESOLVE_CONFIDENCE:
        return _unresolved(raw, "low_confidence", [best["generic"]])

    return {
        "status": "resolved",
        "input": raw,
        "generic": best["generic"],
        "confidence": confidence,
        "verified": verified,
        "source": best["source"],
        "source_ref": best["source_ref"],
        "source_accessed": best["source_accessed"],
        "match_type": match_type,  # exact | generic | fuzzy — the basis of `confidence`
        "matched_name": best["name"],
        "strength": best["strength"],
        "strength_matched": strength_matched,
        "aliases": _aliases_of(index, best["drug_id"]),
    }


def _fuzzy(raw: str, key: str, strength, index: dict) -> dict | None:
    if len(key) < FUZZY_MIN_LEN:
        return None
    by_key = index["by_key"]
    close = difflib.get_close_matches(key, by_key.keys(), n=6, cutoff=FUZZY_MIN_RATIO)
    if not close:
        return None
    scored = sorted(((difflib.SequenceMatcher(None, key, k).ratio(), k) for k in close), reverse=True)
    best_ratio, best_key = scored[0]
    best_drugs = {e["drug_id"] for e in by_key[best_key]}
    rival = [e for r, k in scored[1:] if best_ratio - r < FUZZY_MARGIN for e in by_key[k]
             if e["drug_id"] not in best_drugs]
    if rival:  # two different drugs are about equally close: ambiguous, ask
        return _unresolved(raw, "ambiguous", [e["generic"] for e in by_key[best_key] + rival])
    return _resolve_entries(raw, by_key[best_key], strength, index, match_type="fuzzy", similarity=best_ratio)


def _resolve_uncached(raw: str, strength_arg: str | None) -> dict:
    index = _index()
    by_key = index["by_key"]
    keys, strength = _split_input(raw, strength_arg)
    if not keys:
        return _unresolved(raw, "empty_input")

    for key in keys:  # exact (brand first, then generic/alias)
        entries = by_key.get(key)
        if entries:
            kind = "exact" if any(e["kind"] == "brand" for e in entries) else "generic"
            return _resolve_entries(raw, entries, strength, index, match_type=kind)

    result = _fuzzy(raw, keys[-1], strength, index)
    return result or _unresolved(raw, "no_match")


def resolve_brand(brand: str, strength: str | None = None) -> dict:
    """Resolve a locally used brand name (or a generic/alias) to a generic drug. Never guesses."""
    raw = (brand or "").strip()
    if not raw:
        return _unresolved(brand or "", "empty_input")
    if len(raw) > MAX_INPUT_LEN:
        return _unresolved(raw[:MAX_INPUT_LEN], "input_too_long")
    return _cached("resolve", (raw.lower(), (strength or "").strip().lower()), lambda: _resolve_uncached(raw, strength))


# ---------------------------------------------------------------------------------------------------------------
# lookup_drug
# ---------------------------------------------------------------------------------------------------------------
def _find_drug(name: str, index: dict) -> dict | None:
    """Exact generic-name or alias match only (no brands, no fuzzy): the tools below take generic names."""
    for e in index["by_key"].get(_key(name), []):
        if e["kind"] == "generic":
            return {"id": e["drug_id"], "generic": e["generic"]}
    return None


def _lookup_uncached(name: str) -> dict:
    from apps.knowledge.models import KnowledgeDocument  # local import: knowledge depends on drugs

    index = _index()
    drug = _find_drug(name, index)
    if not drug:
        return {"status": "not_found", "input": name}
    docs = KnowledgeDocument.objects.filter(drug_id=drug["id"]).order_by("-fetched_at")
    brand_names = (BrandMapping.objects.filter(drug_id=drug["id"]).order_by("brand_name")
                   .values_list("brand_name", flat=True).distinct())
    return {
        "status": "found",
        "input": name,
        "generic_name": drug["generic"],
        "aliases": _aliases_of(index, drug["id"]),
        "brand_names": list(brand_names[:20]),
        "sources": [
            {"source": d["source"], "title": d["title"], "source_url": d["source_url"],
             "license_note": d["license_note"]}
            for d in docs.values("source", "title", "source_url", "license_note")[:10]
        ],
        "document_count": docs.count(),
        "interaction_records": Interaction.objects.filter(Q(drug_a_id=drug["id"]) | Q(drug_b_id=drug["id"])).count(),
    }


def lookup_drug(generic_name: str) -> dict:
    """Basic record for a generic drug (or alias), with the sources that mention it."""
    name = (generic_name or "").strip()
    if not name or len(name) > MAX_INPUT_LEN:
        return {"status": "not_found", "input": generic_name or ""}
    return _cached("lookup", (_key(name),), lambda: _lookup_uncached(name))


# ---------------------------------------------------------------------------------------------------------------
# check_interaction
# ---------------------------------------------------------------------------------------------------------------
def _record(i: Interaction) -> dict:
    return {"severity": i.severity, "mechanism": i.mechanism, "management": i.management, "source": i.source,
            "source_ref": i.source_ref, "license_note": i.license_note}


def _no_record(a: str, b: str, reason: str, unknown: list[str] | None = None) -> dict:
    out = {"status": "no_record", "drug_a": a, "drug_b": b, "reason": reason, "note": NO_RECORD_NOTE}
    if unknown:
        out["unknown_drugs"] = unknown
    return out


def _check_uncached(drug_a: str, drug_b: str) -> dict:
    index = _index()
    a, b = _find_drug(drug_a, index), _find_drug(drug_b, index)
    if not a or not b:
        return _no_record(drug_a, drug_b, "drug_not_found",
                          [n for n, found in ((drug_a, a), (drug_b, b)) if not found])
    if a["id"] == b["id"]:
        return _no_record(a["generic"], b["generic"], "same_drug")

    x, y = Interaction.canonical(a["id"], b["id"])
    rows = list(Interaction.objects.filter(drug_a_id=x, drug_b_id=y))
    if not rows:
        return _no_record(a["generic"], b["generic"], "no_interaction_record")

    rows.sort(key=lambda r: (-SEVERITY_RANK.get(r.severity, 0), r.source))
    out = {"status": "found", "drug_a": a["generic"], "drug_b": b["generic"], **_record(rows[0])}
    if len(rows) > 1:  # several sources: primary = most severe; the rest are kept so a conflict stays visible
        out["other_records"] = [_record(r) for r in rows[1:]]
        out["severity_conflict"] = len({r.severity for r in rows if r.severity != "unknown"}) > 1
    return out


def check_interaction(drug_a: str, drug_b: str) -> dict:
    """Interaction record for a pair of generic names. 'no_record' means no evidence found — NOT that it is safe."""
    a, b = (drug_a or "").strip(), (drug_b or "").strip()
    if not a or not b or len(a) > MAX_INPUT_LEN or len(b) > MAX_INPUT_LEN:
        return _no_record(drug_a or "", drug_b or "", "invalid_input")
    return _cached("interaction", (_key(a), _key(b)), lambda: _check_uncached(a, b))


# ---------------------------------------------------------------------------------------------------------------
# search (autocomplete)
# ---------------------------------------------------------------------------------------------------------------
def search_drugs(q: str, limit: int = 10) -> list[dict]:
    """Autocomplete over brand + generic + alias names. Exact > starts-with > word-starts-with > contains."""
    needle = _key(q)
    limit = max(1, min(int(limit), SEARCH_MAX_LIMIT))
    if len(needle) < 2:
        return []

    def score(key: str) -> int | None:
        if key == needle:
            return 0
        if key.startswith(needle):
            return 1
        if any(w.startswith(needle) for w in key.split()):
            return 2
        return 3 if needle in key else None

    hits = []
    for key, entries in _index()["by_key"].items():
        s = score(key)
        if s is None:
            continue
        for e in entries:
            hits.append((s, 0 if e["kind"] == "brand" else 1, len(e["name"]), e["name"].lower(), e))
    hits.sort(key=lambda t: t[:4])

    results, seen = [], set()
    for *_, e in hits:
        ident = (e["kind"], e["name"].lower(), e["strength"], e["drug_id"])
        if ident in seen:
            continue
        seen.add(ident)
        results.append({
            "type": e["kind"], "name": e["name"], "generic": e["generic"], "strength": e["strength"],
            "dosage_form": e["dosage_form"], "verified": e["verified"], "source": e["source"],
            "source_ref": e["source_ref"], "source_accessed": e["source_accessed"],
        })
        if len(results) >= limit:
            break
    return results
