"""Strict loaders for curated drug data.

Imported brand mappings are never allowed to mark themselves as reviewed. Only the admin review
workflow can set `verified=True`.
"""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction

from . import services
from .models import BrandMapping, Drug

REQUIRED_BRAND_COLUMNS = (
    "brand_name", "generic_name", "source", "source_ref", "source_accessed", "confidence",
)
TRUE_VALUES = {"true", "yes", "1", "y"}
FALSE_VALUES = {"false", "no", "0", "n", ""}
EMPTY_REFERENCES = {"tbd", "n/a", "na", "none", "unknown"}


def parse_brand_rows(path: Path) -> dict:
    """Validate a mapping CSV without writing rows; errors identify the source line."""
    names: dict[str, list[Drug]] = {}
    for drug in Drug.objects.all():
        names.setdefault(drug.generic_name.strip().lower(), []).append(drug)
        for alias in drug.aliases or []:
            if isinstance(alias, str) and alias.strip():
                names.setdefault(alias.strip().lower(), []).append(drug)

    ok, errors, seen = [], [], set()
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = {str(h or "").strip().lower() for h in (reader.fieldnames or [])}
        missing_headers = [column for column in REQUIRED_BRAND_COLUMNS if column not in headers]
        if missing_headers:
            raise ValueError(f"Missing column(s): {', '.join(missing_headers)}")

        for line, raw in enumerate(reader, start=2):
            row = {str(key or "").strip().lower(): (value or "").strip()
                   for key, value in raw.items() if key}
            problems = []
            for column in REQUIRED_BRAND_COLUMNS:
                if not row.get(column):
                    problems.append(f"missing {column}")
            if row.get("source_ref", "").lower() in EMPTY_REFERENCES:
                problems.append("source_ref must identify the supporting record or document")

            verified = row.get("verified", "").lower()
            if verified not in TRUE_VALUES | FALSE_VALUES:
                problems.append(f"bad verified value {verified!r}")
            elif verified in TRUE_VALUES:
                problems.append("verified can only be set after review in Django admin")

            try:
                confidence = Decimal(row.get("confidence", ""))
                if not confidence.is_finite() or not 0 <= confidence <= 1:
                    problems.append("confidence must be between 0 and 1")
            except InvalidOperation:
                confidence = None
                problems.append("confidence is not a number")

            try:
                source_accessed = date.fromisoformat(row.get("source_accessed", ""))
            except ValueError:
                source_accessed = None
                problems.append("source_accessed must be an ISO date (YYYY-MM-DD)")

            brand = row.get("brand_name", "")
            generic = row.get("generic_name", "").lower()
            if len(brand) > 120 or len(row.get("strength", "")) > 40 or len(row.get("dosage_form", "")) > 30:
                problems.append("mapping field exceeds its maximum length")
            if len(row.get("source", "")) > 60 or len(row.get("source_ref", "")) > 500:
                problems.append("source field exceeds its maximum length")

            candidates = list({drug.pk: drug for drug in names.get(generic, [])}.values())
            if not candidates:
                problems.append(f"generic {row.get('generic_name', '')!r} not found in Drug table")
                drug = None
            elif len(candidates) > 1:
                problems.append(f"generic or alias {row.get('generic_name', '')!r} is ambiguous")
                drug = None
            else:
                drug = candidates[0]

            mapping_key = None
            if drug is not None:
                mapping_key = (brand.lower(), row.get("strength", "").lower(),
                               row.get("dosage_form", "").lower(), drug.pk)
                if mapping_key in seen:
                    problems.append("duplicate mapping row")

            if problems:
                errors.append((line, brand, "; ".join(problems)))
            else:
                if mapping_key is None:
                    raise RuntimeError("Validated brand row has no resolved drug")
                seen.add(mapping_key)
                ok.append((row, drug, False, confidence, source_accessed))

    return {"ok": ok, "errors": errors, "BrandMapping": BrandMapping}


@transaction.atomic
def save_brand_rows(parsed: dict) -> dict:
    """Upsert validated rows. Re-imports preserve review only when every imported value is unchanged."""
    created = updated = 0
    for row, drug, _verified, confidence, source_accessed in parsed["ok"]:
        defaults = {
            "source": row["source"],
            "source_ref": row["source_ref"],
            "source_accessed": source_accessed,
            "confidence": confidence,
        }
        lookup = {
            "brand_name": row["brand_name"],
            "strength": row.get("strength", ""),
            "dosage_form": row.get("dosage_form", ""),
            "drug": drug,
        }
        existing = BrandMapping.objects.filter(**lookup).first()
        if existing is None:
            BrandMapping.objects.create(**lookup, **defaults, verified=False)
            created += 1
            continue

        changed = any(getattr(existing, field) != value for field, value in defaults.items())
        if changed:
            for field, value in defaults.items():
                setattr(existing, field, value)
            existing.verified = False
            existing.save(update_fields=[*defaults, "verified"])
            updated += 1

    if created or updated:
        services.invalidate_cache()
    return {"created": created, "updated": updated}
