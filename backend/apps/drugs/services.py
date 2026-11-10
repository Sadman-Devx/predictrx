"""Reference-data services for the drugs app (Day 3, Backend Dev).

Safety rules enforced here (docs/rule.md §3, §4, §6):
* A row that names an unknown or ambiguous drug is SKIPPED and counted. We never auto-create a Drug.
* Every Interaction stores source + license_note. A row without them is rejected.
* BrandMapping.verified is always False on load. Re-loading never touches an existing row.
* Loads are idempotent: the same input twice gives the same table contents.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator

from django.db import transaction
from django.db.models import Prefetch, Q, QuerySet

from .models import BrandMapping, Drug, Interaction

SEVERITY_RANK = {"unknown": 0, "minor": 1, "moderate": 2, "major": 3}
DEFAULT_LICENSES = {"ddinter": "CC BY-NC-SA 4.0 — non-commercial"}
INPUT_FORMATS = ("jsonl", "csv", "ddinter-csv")
_INTERACTION_UPDATE_FIELDS = ["severity", "mechanism", "management", "source_ref", "license_note"]


def _max_len(model, field_name: str) -> int:
    return model._meta.get_field(field_name).max_length


@dataclass
class LoadStats:
    rows_read: int = 0
    created: int = 0
    updated: int = 0
    skipped: Counter = field(default_factory=Counter)
    notes: Counter = field(default_factory=Counter)
    dry_run: bool = False

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())

    def as_dict(self) -> dict:
        return {
            "rows_read": self.rows_read, "created": self.created, "updated": self.updated,
            "skipped_total": self.skipped_total, "skipped": dict(self.skipped),
            "notes": dict(self.notes), "dry_run": self.dry_run,
        }


# ---------------- name matching ----------------

def normalize_name(value) -> str:
    return " ".join(str(value or "").lower().split())


def build_name_index() -> dict[str, int | None]:
    """generic names win; an alias claimed by two drugs maps to None (ambiguous, never guessed)."""
    rows = list(Drug.objects.values_list("id", "generic_name", "aliases"))
    index: dict[str, int | None] = {normalize_name(name): drug_id for drug_id, name, _ in rows}
    generic_names = set(index)
    for drug_id, _, aliases in rows:
        for alias in aliases or []:
            key = normalize_name(alias) if isinstance(alias, str) else ""
            if not key or key in generic_names:
                continue
            index[key] = None if (key in index and index[key] != drug_id) else drug_id
    return index


def resolve_drug_id(name, index):
    key = normalize_name(name)
    if not key:
        return None, "missing_drug_name"
    if key not in index:
        return None, "unknown_drug"
    if index[key] is None:
        return None, "ambiguous_drug_name"
    return index[key], None


def canonical_pair(a_id: int, b_id: int) -> tuple[int, int]:
    return Interaction.canonical(a_id, b_id)


# ---------------- interaction loader ----------------

def _clean_severity(value, stats: LoadStats) -> str:
    sev = normalize_name(value)
    if sev in SEVERITY_RANK:
        return sev
    stats.notes["severity_normalized_to_unknown"] += 1  # never guess a level upward
    return "unknown"


def _parse_interaction_row(row: dict, index, stats: LoadStats) -> dict | None:
    def skip(reason: str) -> None:
        stats.skipped[reason] += 1
        return None

    source = normalize_name(row.get("source"))
    if not source:
        return skip("missing_source")
    a_id, reason = resolve_drug_id(row.get("drug_a_name"), index)
    if reason:
        return skip(reason)
    b_id, reason = resolve_drug_id(row.get("drug_b_name"), index)
    if reason:
        return skip(reason)
    if a_id == b_id:
        return skip("self_interaction")

    license_note = str(row.get("license_note") or "").strip() or DEFAULT_LICENSES.get(source, "")
    if not license_note:
        return skip("missing_license_note")
    source_ref = str(row.get("source_ref") or "").strip()
    if (len(source) > _max_len(Interaction, "source")
            or len(source_ref) > _max_len(Interaction, "source_ref")
            or len(license_note) > _max_len(Interaction, "license_note")):
        return skip("field_too_long")  # never truncate a source or a license

    lo, hi = canonical_pair(a_id, b_id)
    return {
        "drug_a_id": lo, "drug_b_id": hi, "source": source,
        "severity": _clean_severity(row.get("severity"), stats),
        "mechanism": str(row.get("mechanism") or "").strip(),
        "management": str(row.get("management") or "").strip(),
        "source_ref": source_ref, "license_note": license_note,
    }


def import_interactions(rows: Iterable[dict], *, dry_run: bool = False, batch_size: int = 1000) -> LoadStats:
    """Idempotent upsert. A-B and B-A collapse to one row; on disagreement the MORE severe level is kept."""
    stats = LoadStats(dry_run=dry_run)
    index = build_name_index()
    pending: dict[tuple[int, int, str], dict] = {}

    for row in rows:
        stats.rows_read += 1
        parsed = _parse_interaction_row(row, index, stats)
        if parsed is None:
            continue
        key = (parsed["drug_a_id"], parsed["drug_b_id"], parsed["source"])
        previous = pending.get(key)
        if previous is None:
            pending[key] = parsed
        elif previous["severity"] != parsed["severity"]:
            stats.notes["severity_conflict_resolved"] += 1
            if SEVERITY_RANK[parsed["severity"]] > SEVERITY_RANK[previous["severity"]]:
                pending[key] = parsed
        else:
            stats.notes["duplicate_in_input"] += 1

    with transaction.atomic():
        existing = set(Interaction.objects.filter(source__in={k[2] for k in pending})
                       .values_list("drug_a_id", "drug_b_id", "source"))
        objs = []
        for key, parsed in pending.items():
            if key in existing:
                stats.updated += 1
            else:
                stats.created += 1
            objs.append(Interaction(**parsed))
        for start in range(0, len(objs), batch_size):
            Interaction.objects.bulk_create(
                objs[start:start + batch_size], update_conflicts=True,
                unique_fields=["drug_a", "drug_b", "source"], update_fields=_INTERACTION_UPDATE_FIELDS,
            )
        if dry_run:
            transaction.set_rollback(True)
    return stats


# ---------------- brand mapping loader ----------------

def _parse_confidence(value) -> Decimal | None:
    text = str(value if value is not None else "").strip()
    if not text:
        return Decimal("0.00")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not Decimal("0") <= number <= Decimal("1"):
        return None
    return number.quantize(Decimal("0.01"))


def _brand_key(brand, strength, form):
    return (normalize_name(brand), normalize_name(strength), normalize_name(form))


def import_brand_mappings(rows: Iterable[dict], *, dry_run: bool = False) -> LoadStats:
    """verified is ALWAYS False; existing rows are left untouched (a pharmacist's review is never reset)."""
    stats = LoadStats(dry_run=dry_run)
    index = build_name_index()

    seen: set[tuple[str, str, str, int]] = set()
    drugs_by_brand: dict[tuple[str, str, str], set[int]] = {}
    for brand, strength, form, drug_id in BrandMapping.objects.values_list(
            "brand_name", "strength", "dosage_form", "drug_id"):
        key = _brand_key(brand, strength, form)
        seen.add((*key, drug_id))
        drugs_by_brand.setdefault(key, set()).add(drug_id)

    new_objs: list[BrandMapping] = []
    for row in rows:
        stats.rows_read += 1
        brand = str(row.get("brand_name") or "").strip()
        if not brand:
            stats.skipped["missing_brand_name"] += 1
            continue
        source = str(row.get("source") or "").strip()
        if not source:
            stats.skipped["missing_source"] += 1
            continue
        drug_id, reason = resolve_drug_id(row.get("generic_name"), index)
        if reason:
            stats.skipped[reason] += 1
            continue
        confidence = _parse_confidence(row.get("confidence"))
        if confidence is None:
            stats.skipped["bad_confidence"] += 1
            continue
        strength = str(row.get("strength") or "").strip()
        form = str(row.get("dosage_form") or "").strip()
        if (len(brand) > _max_len(BrandMapping, "brand_name") or len(source) > _max_len(BrandMapping, "source")
                or len(strength) > _max_len(BrandMapping, "strength")
                or len(form) > _max_len(BrandMapping, "dosage_form")):
            stats.skipped["field_too_long"] += 1
            continue

        key = _brand_key(brand, strength, form)
        if (*key, drug_id) in seen:
            stats.notes["existing_left_unchanged"] += 1
            continue
        if drugs_by_brand.get(key) and drug_id not in drugs_by_brand[key]:
            stats.notes["same_brand_multiple_generics"] += 1
        seen.add((*key, drug_id))
        drugs_by_brand.setdefault(key, set()).add(drug_id)
        new_objs.append(BrandMapping(brand_name=brand, strength=strength, dosage_form=form, drug_id=drug_id,
                                     source=source, verified=False, confidence=confidence))

    with transaction.atomic():
        BrandMapping.objects.bulk_create(new_objs)
        stats.created = len(new_objs)
        if dry_run:
            transaction.set_rollback(True)
    return stats


# ---------------- file readers ----------------

def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{line_no}: invalid JSON ({exc.msg})") from exc


def iter_csv(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def iter_ddinter_csv(path: Path) -> Iterator[dict]:
    """ASSUMED header (verify against the real file): Drug_A, Drug_B, Level. Other header -> ValueError."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = {(name or "").strip().lower(): name for name in (reader.fieldnames or [])}
        missing = [c for c in ("drug_a", "drug_b", "level") if c not in columns]
        if missing:
            raise ValueError(f"{path.name}: DDInter header not recognised, missing {missing}; "
                             f"found {list(reader.fieldnames or [])}")
        for row in reader:
            yield {
                "drug_a_name": row[columns["drug_a"]], "drug_b_name": row[columns["drug_b"]],
                "severity": row[columns["level"]], "source": "ddinter",
                "source_ref": f"DDInter 2.0 file: {path.name}",
            }


_READERS = {"jsonl": iter_jsonl, "csv": iter_csv, "ddinter-csv": iter_ddinter_csv}
_GLOBS = {"jsonl": "*.jsonl", "csv": "*.csv", "ddinter-csv": "*.csv"}


def detect_format(path: Path, default: str = "jsonl") -> str:
    if path.is_dir():
        return default
    return "jsonl" if path.suffix.lower() == ".jsonl" else "csv" if path.suffix.lower() == ".csv" else default


def iter_rows(path: Path, fmt: str) -> Iterator[dict]:
    if fmt not in _READERS:
        raise ValueError(f"unknown format {fmt!r}; use one of {INPUT_FORMATS}")
    if not path.exists():
        raise FileNotFoundError(path)
    files = sorted(path.glob(_GLOBS[fmt])) if path.is_dir() else [path]
    if not files:
        raise FileNotFoundError(f"no {_GLOBS[fmt]} files in {path}")
    for file in files:
        yield from _READERS[fmt](file)


# ---------------- read queries (used by thin views) ----------------

def drugs_queryset() -> QuerySet[Drug]:
    return Drug.objects.order_by("generic_name")


def drug_detail_queryset() -> QuerySet[Drug]:
    from apps.knowledge.models import KnowledgeDocument  # local import: knowledge depends on drugs
    return drugs_queryset().prefetch_related(
        Prefetch("documents", queryset=KnowledgeDocument.objects.only("id", "drug_id", "source")))


def interactions_queryset() -> QuerySet[Interaction]:
    return Interaction.objects.select_related("drug_a", "drug_b").order_by(
        "drug_a__generic_name", "drug_b__generic_name", "source", "id")


def involving_drug(queryset: QuerySet[Interaction], drug_id: int) -> QuerySet[Interaction]:
    return queryset.filter(Q(drug_a_id=drug_id) | Q(drug_b_id=drug_id))
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
