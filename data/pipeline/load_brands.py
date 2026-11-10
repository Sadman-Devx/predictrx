"""Load the curated brand→generic sheet (data/brands/brand_mapping.csv) into BrandMapping.

Validation is strict: a row without a `source`, with an unknown generic, or with a bad confidence is REPORTED and
(by default) stops the load — nothing is silently skipped. `verified` defaults to false.
Idempotent: re-running updates existing rows instead of duplicating them.

Run:  python data/pipeline/load_brands.py [--file data/brands/brand_mapping.csv] [--skip-bad]
"""
import argparse
import csv
from pathlib import Path

from common import REPO_ROOT, django_setup

DEFAULT_FILE = REPO_ROOT / "data" / "brands" / "brand_mapping.csv"
REQUIRED = ["brand_name", "generic_name", "source", "confidence"]
TRUE, FALSE = {"true", "yes", "1", "y"}, {"false", "no", "0", "n", ""}


def load_rows(path: Path) -> dict:
    from apps.drugs import services
    from apps.drugs.models import BrandMapping

    services.clear_index_cache()
    ok, errors = [], []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):  # line 1 is the header
            row = {k: (v or "").strip() for k, v in row.items() if k}
            problems = [f"missing {c}" for c in REQUIRED if not row.get(c)]
            verified_raw = row.get("verified", "").lower()
            if verified_raw not in TRUE | FALSE:
                problems.append(f"bad verified value {verified_raw!r}")
            try:
                conf = float(row.get("confidence", ""))
                if not 0 <= conf <= 1:
                    problems.append("confidence must be between 0 and 1")
            except ValueError:
                conf = None
                problems.append("confidence is not a number")
            drug_id = None
            if row.get("generic_name"):
                res = services.resolve_name(row["generic_name"], allow_brands=False)
                if res["status"] == "resolved":
                    drug_id = res["drug_id"]
                else:
                    problems.append(f"generic {row['generic_name']!r} not found/ambiguous in Drug table")
            if problems:
                errors.append((n, row.get("brand_name", ""), "; ".join(problems)))
            else:
                ok.append((row, drug_id, verified_raw in TRUE, conf))

    return {"ok": ok, "errors": errors, "BrandMapping": BrandMapping}


def save(parsed: dict) -> dict:
    BrandMapping = parsed["BrandMapping"]
    created = updated = 0
    for row, drug_id, verified, conf in parsed["ok"]:
        obj, was_created = BrandMapping.objects.update_or_create(
            brand_name=row["brand_name"], strength=row.get("strength", ""), dosage_form=row.get("dosage_form", ""),
            drug_id=drug_id,
            defaults={"source": row["source"], "verified": verified, "confidence": conf},
        )
        created += was_created
        updated += not was_created
    return {"created": created, "updated": updated}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    ap.add_argument("--skip-bad", action="store_true", help="load the valid rows even if some rows are invalid")
    args = ap.parse_args()
    django_setup()
    if not args.file.exists():
        raise SystemExit(f"{args.file} not found. Copy data/brands/brand_mapping_template.csv and fill it.")
    parsed = load_rows(args.file)
    for line, brand, msg in parsed["errors"]:
        print(f"  line {line} ({brand or '?'}): {msg}")
    if parsed["errors"] and not args.skip_bad:
        raise SystemExit(f"{len(parsed['errors'])} invalid rows — fix them or use --skip-bad. Nothing was loaded.")
    stats = save(parsed)
    print(f"valid rows: {len(parsed['ok'])}  invalid: {len(parsed['errors'])}  "
          f"created: {stats['created']}  updated: {stats['updated']}")


if __name__ == "__main__":
    main()