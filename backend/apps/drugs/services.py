"""Drug lookup services: resolve names, look up drugs, check interactions.

Plain functions (no HTTP). Used by the REST API, the MCP server and the LangGraph agents, so all of them
answer from the same tables. Rules built in (docs/rule.md):
  * never guess a brand/generic match — ambiguous or fuzzy-only input is returned as `unresolved` with candidates
  * "no record" is NOT "safe"; severity "unknown" is NOT "safe"
  * every found interaction carries evidence references
"""
import difflib
import time
from dataclasses import dataclass
from itertools import combinations

from django.db.models import Q

from .models import BrandMapping, Drug, Interaction
from .names import key, parse_input, strip_salt

NO_RECORD_NOTE = "No interaction record found. This does not mean the combination is safe."
UNKNOWN_SEVERITY_NOTE = "A record exists but its severity is unknown. This is not evidence that the combination is safe."
SEVERITY_ORDER = {"unknown": 0, "minor": 1, "moderate": 2, "major": 3}
_INDEX_TTL_SECONDS = 300


# ---------------------------------------------------------------------------------------------- name index
@dataclass
class DrugIndex:
    by_key: dict      # normalised name/alias -> [drug ids]
    drugs: dict       # id -> {"id", "generic_name", "aliases"}
    keys: list


_index: DrugIndex | None = None
_index_at = 0.0


def clear_index_cache() -> None:
    """Call after loading data (pipeline/tests). Otherwise the index refreshes itself every few minutes."""
    global _index, _index_at
    _index, _index_at = None, 0.0


def get_index() -> DrugIndex:
    global _index, _index_at
    if _index is None or time.time() - _index_at > _INDEX_TTL_SECONDS:
        by_key: dict[str, list[int]] = {}
        drugs: dict[int, dict] = {}
        for d in Drug.objects.only("id", "generic_name", "aliases"):
            drugs[d.id] = {"id": d.id, "generic_name": d.generic_name, "aliases": list(d.aliases or [])}
            for name in (d.generic_name, *(d.aliases or [])):
                ids = by_key.setdefault(key(name), [])
                if d.id not in ids:
                    ids.append(d.id)
        _index, _index_at = DrugIndex(by_key, drugs, sorted(by_key)), time.time()
    return _index


def _drug_ref(drug_id: int) -> dict:
    d = get_index().drugs[drug_id]
    return {"id": d["id"], "generic_name": d["generic_name"]}


# ---------------------------------------------------------------------------------------------- resolve
def _suggestions(text: str, limit: int = 3) -> list[dict]:
    idx = get_index()
    out, seen = [], set()
    if "(" in text:  # "ibuprofen (topical)": offer the plain drug first, clearly marked as a different formulation
        base = text.split("(")[0].strip()
        for drug_id in idx.by_key.get(base, []):
            seen.add(drug_id)
            out.append({**_drug_ref(drug_id), "matched_text": base, "score": 0.99,
                        "note": "the plain drug exists, but not this formulation/route"})
    for match in difflib.get_close_matches(text, idx.keys, n=8, cutoff=0.72):
        score = round(difflib.SequenceMatcher(None, text, match).ratio(), 2)
        for drug_id in idx.by_key[match]:
            if drug_id not in seen:
                seen.add(drug_id)
                out.append({**_drug_ref(drug_id), "matched_text": match, "score": score})
    return sorted(out, key=lambda s: -s["score"])[:limit]


def resolve_name(raw: str, strength: str | None = None, *, allow_brands: bool = True) -> dict:
    """Resolve typed text (generic, alias, salt form, or local brand) to ONE drug — or say it cannot.

    resolved   -> {"status": "resolved", "drug": {...}, "generic": "...", "method", "confidence", "verified", ...}
    unresolved -> {"status": "unresolved", "reason": "empty|not_found|ambiguous", "candidates": [...], "suggestions": [...]}
    Fuzzy matches are only ever SUGGESTIONS; the user must confirm them.
    """
    parsed = parse_input(raw or "")
    text = parsed["text"]
    strength = strength or parsed["strength"]
    base = {"input": raw, "parsed": {"text": text, "strength": strength}}
    if not text:
        return {**base, "status": "unresolved", "reason": "empty", "candidates": [], "suggestions": []}

    idx = get_index()
    candidates: dict[int, dict] = {}  # drug_id -> how it matched

    # 1) exact generic name / alias; then salt-stripped ("metformin hydrochloride" -> "metformin")
    method = None
    attempts = [("exact", text)]
    if "(" not in text:  # a route/formulation in brackets ("... (topical)") must never be dropped silently
        attempts.append(("salt_stripped", strip_salt(text)))
    for attempt, probe in attempts:
        ids = idx.by_key.get(probe)
        if ids:
            method = "generic_name" if attempt == "exact" and probe == idx.drugs[ids[0]]["generic_name"] else (
                "alias" if attempt == "exact" else "salt_stripped")
            for i in ids:
                candidates[i] = {"method": method, "confidence": 1.0 if attempt == "exact" else 0.95,
                                 "verified": None, "source": "drug_table"}
            break

    # 2) curated brand sheet
    if allow_brands:
        rows = list(BrandMapping.objects.filter(brand_name__iexact=text).select_related("drug"))
        if strength:
            exact_strength = [r for r in rows if key(r.strength).replace(" ", "") == strength]
            rows = exact_strength or rows
        for r in rows:
            if r.drug_id not in candidates:
                candidates[r.drug_id] = {"method": "brand_mapping", "confidence": float(r.confidence),
                                         "verified": r.verified, "source": r.source}

    if len(candidates) == 1:
        drug_id, info = next(iter(candidates.items()))
        notes = []
        if info["method"] == "brand_mapping" and not info["verified"]:
            notes.append("Brand mapping is not yet verified by a pharmacist/mentor.")
        return {**base, "status": "resolved", "drug": _drug_ref(drug_id), "drug_id": drug_id,
                "generic": idx.drugs[drug_id]["generic_name"], **info, "notes": notes}
    if len(candidates) > 1:
        return {**base, "status": "unresolved", "reason": "ambiguous", "suggestions": [],
                "candidates": [{**_drug_ref(i), **info} for i, info in candidates.items()]}
    return {**base, "status": "unresolved", "reason": "not_found", "candidates": [],
            "suggestions": _suggestions(text)}


def resolve_brand(brand: str, strength: str | None = None) -> dict:
    """MCP-facing alias of resolve_name (brand names AND generics are accepted)."""
    return resolve_name(brand, strength)


def search_names(q: str, limit: int = 10) -> list[dict]:
    """Autocomplete over generic names, aliases and brand names (prefix first, then substring)."""
    q = key(q)
    if len(q) < 2:
        return []
    idx = get_index()
    hits: list[dict] = []
    seen: set = set()
    starts = [k for k in idx.keys if k.startswith(q)]
    contains = [k for k in idx.keys if q in k and not k.startswith(q)]
    for k in starts + contains:
        for drug_id in idx.by_key[k]:
            if (drug_id, k) not in seen:
                seen.add((drug_id, k))
                kind = "generic" if k == idx.drugs[drug_id]["generic_name"] else "alias"
                hits.append({"kind": kind, "text": k, **_drug_ref(drug_id)})
    brands = BrandMapping.objects.filter(brand_name__icontains=q).select_related("drug")[:limit]
    for b in brands:
        hits.append({"kind": "brand", "text": b.brand_name, **_drug_ref(b.drug_id)})
    return hits[:limit]


# ---------------------------------------------------------------------------------------------- lookup
def lookup_drug(name: str) -> dict:
    from apps.knowledge.models import Chunk, KnowledgeDocument

    res = resolve_name(name, allow_brands=True)
    if res["status"] != "resolved":
        return {"status": "not_found" if res["reason"] != "ambiguous" else "ambiguous", "input": name,
                "candidates": res["candidates"], "suggestions": res["suggestions"]}
    drug = Drug.objects.get(pk=res["drug_id"])
    gname = drug.generic_name
    variants = list(Drug.objects.filter(generic_name__startswith=f"{gname} (").values_list("generic_name", flat=True))
    return {
        "status": "found", "drug": {"id": drug.id, "generic_name": gname}, "aliases": drug.aliases,
        "formulation_variants": sorted(variants),
        "external_ids": drug.external_ids,
        "sources": {
            "label_documents": KnowledgeDocument.objects.filter(drug=drug).count(),
            "has_interactions_section": Chunk.objects.filter(document__drug=drug, section="DRUG INTERACTIONS").exists(),
            "interaction_records": Interaction.objects.filter(Q(drug_a=drug) | Q(drug_b=drug)).count(),
        },
    }


# ---------------------------------------------------------------------------------------------- interactions
def _record(ix: Interaction) -> dict:
    return {"id": ix.id, "severity": ix.severity, "source": ix.source, "source_ref": ix.source_ref,
            "license_note": ix.license_note, "mechanism": ix.mechanism, "management": ix.management}


def _pair_result(a_id: int, b_id: int, records: list[Interaction]) -> dict:
    out = {"drug_a": _drug_ref(a_id), "drug_b": _drug_ref(b_id)}
    if not records:
        return {**out, "status": "no_record", "severity": None, "records": [], "evidence": [], "note": NO_RECORD_NOTE}
    worst = max(records, key=lambda r: SEVERITY_ORDER[r.severity]).severity
    return {
        **out, "status": "found", "severity": worst, "records": [_record(r) for r in records],
        "evidence": [{"type": "interaction", "id": r.id, "source": r.source} for r in records],
        "note": UNKNOWN_SEVERITY_NOTE if worst == "unknown" else "",
    }


def label_mentions(drug_a_id: int, drug_b_id: int, max_per_drug: int = 2, width: int = 220) -> list[dict]:
    """openFDA label passages (DRUG INTERACTIONS section) of one drug that mention the other by name.
    A stop-gap explanation until embedding-based retrieval exists; each hit carries chunk evidence."""
    from apps.knowledge.models import Chunk

    idx = get_index()
    out: list[dict] = []
    for src_id, other_id in ((drug_a_id, drug_b_id), (drug_b_id, drug_a_id)):
        names = {idx.drugs[other_id]["generic_name"], *idx.drugs[other_id]["aliases"]}
        q = Q()
        for n in names:
            q |= Q(text__icontains=n)
        for chunk in Chunk.objects.filter(q, document__drug_id=src_id, section="DRUG INTERACTIONS")[:max_per_drug]:
            low = chunk.text.lower()
            pos = min((low.find(n) for n in names if low.find(n) >= 0), default=0)
            start = max(0, pos - width // 2)
            out.append({
                "from_label_of": _drug_ref(src_id), "mentions": _drug_ref(other_id),
                "snippet": chunk.text[start:start + width].strip(), "section": chunk.section,
                "evidence": {"type": "chunk", "id": chunk.id, "source": "openfda_label"},
            })
    return out


def _unresolved(res: dict) -> dict:
    return {"input": res["input"], "reason": res["reason"], "candidates": res["candidates"],
            "suggestions": res["suggestions"]}


def check_interaction(drug_a: str, drug_b: str, *, include_labels: bool = True) -> dict:
    ra, rb = resolve_name(drug_a), resolve_name(drug_b)
    bad = [_unresolved(r) for r in (ra, rb) if r["status"] != "resolved"]
    if bad:
        return {"status": "unresolved_input", "unresolved": bad}
    if ra["drug_id"] == rb["drug_id"]:
        return {"status": "invalid", "reason": "same_drug", "drug": ra["drug"]}
    lo, hi = Interaction.canonical(ra["drug_id"], rb["drug_id"])
    records = list(Interaction.objects.filter(drug_a_id=lo, drug_b_id=hi))
    result = _pair_result(lo, hi, records)
    if include_labels:
        result["label_mentions"] = label_mentions(lo, hi)
    return result


def check_interactions(names: list[str]) -> dict:
    """Check every pair in a medication list with ONE query. Unresolved names are reported, never dropped."""
    resolved, unresolved, seen = [], [], set()
    for raw in names:
        r = resolve_name(raw)
        if r["status"] != "resolved":
            unresolved.append(_unresolved(r))
        elif r["drug_id"] not in seen:
            seen.add(r["drug_id"])
            resolved.append({"input": raw, **r["drug"]})
    ids = [d["id"] for d in resolved]
    found: dict[tuple[int, int], list[Interaction]] = {}
    if len(ids) > 1:
        for ix in Interaction.objects.filter(drug_a_id__in=ids, drug_b_id__in=ids):
            found.setdefault((ix.drug_a_id, ix.drug_b_id), []).append(ix)
    pairs = []
    for a, b in combinations(sorted(ids), 2):
        pairs.append(_pair_result(a, b, found.get((a, b), [])))
    summary = {s: 0 for s in ("major", "moderate", "minor", "unknown")}
    summary["no_record"] = 0
    for p in pairs:
        summary["no_record" if p["status"] == "no_record" else p["severity"]] += 1
    return {"drugs": resolved, "unresolved": unresolved, "pairs": pairs, "summary": summary}