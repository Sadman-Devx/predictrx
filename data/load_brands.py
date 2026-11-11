"""Stage 4 (store) for the brand -> generic layer: load the curated sheet into drugs.BrandMapping.

CSV columns:  brand_name, strength, dosage_form, generic_name, source, confidence, verified
Rules (docs/rule.md): every row needs a `source`; `verified` stays false until a pharmacist/mentor reviews the row;
the generic must already exist in drugs.Drug (name or alias) — a typo must not silently create a phantom drug.

Idempotent: a row is keyed by (brand_name, strength, dosage_form); re-running updates it, never duplicates it.
Rows that fail validation are reported and skipped; the rest still load.

Run:  python data/pipeline/load_brands.py [path/to/sheet.csv]     (default: fixtures/brand_mapping_sample.csv)
"""
import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from common import django_setup

DEFAULT_CSV = Path(__file__).with_name("fixtures") / "brand_mapping_sample.csv"
TRUE = {"true", "1", "yes", "y"}


def load(path: Path) -> dict:
    from django.db import transaction

    from apps.drugs import services
    from apps.drugs.models import BrandMapping, Drug

    by_name = {}
    for d in Drug.objects.all():
        for n in [d.generic_name, *(d.aliases or [])]:
            by_name.setdefault(str(n).strip().lower(), d)

    stats = {"created": 0, "updated": 0, "skipped": []}
    with path.open(encoding="utf-8-sig", newline="") as f, transaction.atomic():
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            problem = None
            drug = by_name.get(row.get("generic_name", "").lower())
            try:
                conf = Decimal(row.get("confidence") or "0")
            except InvalidOperation:
                conf = Decimal("-1")
            if not row.get("brand_name"):
                problem = "missing brand_name"
            elif not row.get("source"):
                problem = "missing source (every row needs one)"
            elif drug is None:
                problem = f"generic '{row.get('generic_name')}' is not in the Drug table (load/seed it first)"
            elif not Decimal("0") <= conf <= Decimal("1"):
                problem = f"confidence '{row.get('confidence')}' must be between 0 and 1"
            if problem:
                stats["skipped"].append(f"line {line_no}: {problem}")
                continue
            _, created = BrandMapping.objects.update_or_create(
                brand_name=row["brand_name"], strength=row.get("strength", ""), dosage_form=row.get("dosage_form", ""),
                defaults={"drug": drug, "source": row["source"], "confidence": conf,
                          "verified": row.get("verified", "").lower() in TRUE},
            )
            stats["created" if created else "updated"] += 1
    services.invalidate_cache()  # lookups must see the new rows immediately
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("csv", nargs="?", type=Path, default=DEFAULT_CSV)
    args = ap.parse_args()
    django_setup()
    stats = load(args.csv)
    print(f"brand mappings: {stats['created']} created, {stats['updated']} updated, {len(stats['skipped'])} skipped")
    for msg in stats["skipped"]:
        print(f"  SKIPPED {msg}")


if __name__ == "__main__":
    main()
