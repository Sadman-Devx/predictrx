"""Brand -> generic resolver and drug search. Pure business logic (no HTTP).

The MCP tool `resolve_brand` must call `resolve_one` from here, so the API and
the agents always give the same answer.

Rule: never guess. exact brand -> generic/alias -> fuzzy (only if unambiguous
and high score) -> otherwise `unresolved` with suggestions.
"""
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.db.models import Case, IntegerField, When
from rapidfuzz import fuzz, process

from .models import BrandMapping, Drug
from .normalization import normalize_name, parse_input, strength_number

BRAND_INDEX_KEY = "drugs:brand_index:v1"


def _cfg(name: str, default):
    return getattr(settings, name, default)


def clear_brand_index_cache() -> None:
    """Call this after any brand-mapping data reload."""
    cache.delete(BRAND_INDEX_KEY)


def _brand_index() -> list[dict]:
    index = cache.get(BRAND_INDEX_KEY)
    if index is None:
        rows = BrandMapping.objects.select_related("drug")
        index = [
            {
                "brand_name": r.brand_name,
                "norm": normalize_name(r.brand_name),
                "strength_num": strength_number(r.strength),
                "drug_id": r.drug_id,
                "generic": r.drug.generic_name,
                "source": r.source,
                "verified": r.verified,
                "confidence": float(r.confidence or 0),
            }
            for r in rows
        ]
        cache.set(BRAND_INDEX_KEY, index, _cfg("RESOLVER_INDEX_TTL", 300))
    return index


# ---------- result builders ----------

def _resolved(raw, match_type, generic, confidence, verified, source) -> dict:
    return {
        "input": raw,
        "status": "resolved",
        "match_type": match_type,
        "generic": generic,
        "confidence": round(confidence, 2),
        "verified": verified,
        "source": source,
        "suggestions": [],
        "reason": None,
    }


def _unresolved(raw, reason, suggestions=None) -> dict:
    return {
        "input": raw,
        "status": "unresolved",
        "match_type": "none",
        "generic": None,
        "confidence": 0.0,
        "verified": False,
        "source": None,
        "suggestions": suggestions or [],
        "reason": reason,
    }


def _suggestion(row: dict, score: float) -> dict:
    return {
        "brand_name": row["brand_name"],
        "generic_id": row["drug_id"],
        "generic_name": row["generic"],
        "score": round(score, 2),
    }


# ---------- fuzzy ----------

def _fuzzy_candidates(name: str, index: list[dict], min_score: float, limit: int = 5):
    """Return [(row, score 0-1)], one per distinct drug, best first."""
    by_norm: dict[str, list[dict]] = {}
    for row in index:
        by_norm.setdefault(row["norm"], []).append(row)

    matches = process.extract(name, list(by_norm.keys()), scorer=fuzz.ratio, limit=10)
    seen_drugs, out = set(), []
    for choice, score, _ in matches:
        score = score / 100
        if score < min_score:
            break
        for row in by_norm[choice]:
            if row["drug_id"] in seen_drugs:
                continue
            seen_drugs.add(row["drug_id"])
            out.append((row, score))
        if len(out) >= limit:
            break
    return out


# ---------- public API ----------

def resolve_one(raw: str, index: Optional[list[dict]] = None) -> dict:
    parsed = parse_input(raw)
    if not parsed.name:
        return _unresolved(raw, "empty_input")

    index = index if index is not None else _brand_index()

    # 1) exact brand match
    exact = [r for r in index if r["norm"] == parsed.name]
    if exact:
        if parsed.strength_num:
            same_strength = [r for r in exact if r["strength_num"] == parsed.strength_num]
            exact = same_strength or exact
        if len({r["drug_id"] for r in exact}) == 1:
            best = max(exact, key=lambda r: r["confidence"])
            return _resolved(
                raw,
                "exact",
                {"id": best["drug_id"], "name": best["generic"]},
                best["confidence"],
                best["verified"],
                best["source"],
            )
        # same brand maps to different generics -> user must choose
        return _unresolved(raw, "ambiguous", [_suggestion(r, 1.0) for r in exact[:5]])

    # 2) user typed a generic name / alias
    drug = (
        Drug.objects.filter(generic_name=parsed.name).first()
        or Drug.objects.filter(aliases__contains=[parsed.name]).first()
    )
    if drug:
        return _resolved(
            raw,
            "generic",
            {"id": drug.id, "name": drug.generic_name},
            1.0,
            True,
            "drug_table",
        )

    # 3) fuzzy: auto-accept only if high score AND no competing drug
    accept = _cfg("RESOLVER_FUZZY_ACCEPT", 0.90)
    suggest_min = _cfg("RESOLVER_SUGGEST_MIN", 0.75)
    candidates = _fuzzy_candidates(parsed.name, index, suggest_min)
    if candidates:
        top_row, top_score = candidates[0]
        competing = [c for c in candidates[1:] if c[1] >= accept]
        if top_score >= accept and not competing:
            return _resolved(
                raw,
                "fuzzy",
                {"id": top_row["drug_id"], "name": top_row["generic"]},
                min(top_row["confidence"], top_score),
                top_row["verified"],
                top_row["source"],
            )
        return _unresolved(
            raw, "low_confidence", [_suggestion(r, s) for r, s in candidates]
        )

    return _unresolved(raw, "not_found")


def resolve_many(items: list[str]) -> list[dict]:
    index = _brand_index()  # load once for the whole request
    return [resolve_one(raw, index) for raw in items]


def search_drugs(query: str, limit: int = 10) -> list[dict]:
    q = normalize_name(query)
    if len(q) < 2:
        return []

    cache_key = f"drugs:search:{limit}:{q}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    brands = (
        BrandMapping.objects.select_related("drug")
        .filter(brand_name__icontains=q)
        .annotate(
            rank=Case(
                When(brand_name__istartswith=q, then=0),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by("rank", "brand_name")[:limit]
    )
    generics = (
        Drug.objects.filter(generic_name__icontains=q)
        .annotate(
            rank=Case(
                When(generic_name__istartswith=q, then=0),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by("rank", "generic_name")[:limit]
    )

    items = []
    for b in brands:
        label = f"{b.brand_name} {b.strength}".strip() if b.strength else b.brand_name
        items.append(
            {
                "rank": b.rank,
                "type": "brand",
                "label": label,
                "brand_name": b.brand_name,
                "strength": b.strength,
                "generic_id": b.drug_id,
                "generic_name": b.drug.generic_name,
                "verified": b.verified,
            }
        )
    for d in generics:
        items.append(
            {
                "rank": d.rank,
                "type": "generic",
                "label": d.generic_name,
                "brand_name": None,
                "strength": None,
                "generic_id": d.id,
                "generic_name": d.generic_name,
                "verified": True,
            }
        )

    items.sort(key=lambda i: (i["rank"], i["label"].lower()))
    results = [{k: v for k, v in i.items() if k != "rank"} for i in items[:limit]]
    cache.set(cache_key, results, 60)
    return results