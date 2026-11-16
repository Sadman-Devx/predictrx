"""Load the curated brand→generic sheet (data/brands/brand_mapping.csv) into BrandMapping.

Validation is strict: a row without a source reference/access date, with an unknown generic, or with a bad
confidence is REPORTED and (by default) stops the load — nothing is silently skipped. `verified` defaults to false.
Idempotent: re-running updates existing rows instead of duplicating them.

Run:  python data/pipeline/load_brands.py [--file data/brands/brand_mapping.csv] [--skip-bad] [--dry-run]
"""
import argparse
from pathlib import Path

from common import REPO_ROOT, django_setup

DEFAULT_FILE = REPO_ROOT / "data" / "brands" / "brand_mapping.csv"


def load_rows(path: Path) -> dict:
    from apps.drugs.importers import parse_brand_rows

    return parse_brand_rows(path)


def save(parsed: dict) -> dict:
    from apps.drugs.importers import save_brand_rows

    return save_brand_rows(parsed)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    ap.add_argument("--skip-bad", action="store_true", help="load the valid rows even if some rows are invalid")
    ap.add_argument("--dry-run", action="store_true", help="validate rows without writing to the database")
    args = ap.parse_args()
    django_setup()
    if not args.file.exists():
        raise SystemExit(f"{args.file} not found. Copy data/brands/brand_mapping_template.csv and fill it.")
    parsed = load_rows(args.file)
    for line, brand, msg in parsed["errors"]:
        print(f"  line {line} ({brand or '?'}): {msg}")
    if parsed["errors"] and not args.skip_bad:
        raise SystemExit(f"{len(parsed['errors'])} invalid rows — fix them or use --skip-bad. Nothing was loaded.")
    stats = {"created": 0, "updated": 0} if args.dry_run else save(parsed)
    mode = "dry-run (nothing written)" if args.dry_run else "committed"
    print(f"{mode}: valid rows: {len(parsed['ok'])}  invalid: {len(parsed['errors'])}  "
          f"created: {stats['created']}  updated: {stats['updated']}")


if __name__ == "__main__":
    main()