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