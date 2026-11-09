"""Stage 2 — PARSE (DDInter): read the CSVs, validate, and collapse to unique unordered drug pairs.

Input : data/raw/ddinter/ddinter_downloads_code_*.csv   (columns: DDInterID_A, Drug_A, DDInterID_B, Drug_B, Level)
Output: data/processed/ddinter_drugs.jsonl, data/processed/ddinter_pairs.jsonl

These files carry only the severity level — NO mechanism, management text or references. Those exist on the
DDInter website pages but not in the download, so they are left empty here (explanations come from label chunks).
"""
import argparse
import csv
from collections import Counter
from pathlib import Path

from common import PROCESSED_DIR, RAW_DIR, write_jsonl

HEADER = ["DDInterID_A", "Drug_A", "DDInterID_B", "Drug_B", "Level"]
LEVELS = {"major", "moderate", "minor", "unknown"}


def parse_files(files: list[Path]) -> tuple[list[dict], list[dict], Counter]:
    stats: Counter = Counter()
    names: dict[str, str] = {}
    pairs: dict[tuple[str, str], dict] = {}
    for f in files:
        code = f.stem.rsplit("_", 1)[-1]
        with f.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != HEADER:
                raise ValueError(f"{f.name}: unexpected header {reader.fieldnames}")
            for row in reader:
                stats["rows"] += 1
                a, b = row["DDInterID_A"].strip(), row["DDInterID_B"].strip()
                level = row["Level"].strip().lower()
                if not (a and b and row["Drug_A"].strip() and row["Drug_B"].strip()):
                    stats["dropped_empty_field"] += 1
                    continue
                if a == b:
                    stats["dropped_self_pair"] += 1
                    continue
                if level not in LEVELS:
                    stats["dropped_bad_level"] += 1
                    continue
                for ident, name in ((a, row["Drug_A"]), (b, row["Drug_B"])):
                    if names.setdefault(ident, name.strip()) != name.strip():
                        stats["id_with_two_names"] += 1
                key = tuple(sorted((a, b)))
                existing = pairs.get(key)
                if existing is None:
                    pairs[key] = {"id_a": key[0], "id_b": key[1], "level": level, "files": [code]}
                else:
                    stats["duplicate_rows_collapsed"] += 1
                    if code not in existing["files"]:
                        existing["files"].append(code)
                    if existing["level"] != level:
                        stats["conflicting_levels_kept_more_severe"] += 1
                        order = ["unknown", "minor", "moderate", "major"]
                        if order.index(level) > order.index(existing["level"]):
                            existing["level"] = level
    drugs = [{"id": i, "name": n} for i, n in sorted(names.items())]
    return drugs, list(pairs.values()), stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, default=RAW_DIR / "ddinter")
    ap.add_argument("--out-dir", type=Path, default=PROCESSED_DIR)
    args = ap.parse_args()

    files = sorted(args.raw_dir.glob("ddinter_downloads_code_*.csv"))
    if not files:
        raise SystemExit(f"No DDInter CSV files in {args.raw_dir}. Run ingest_ddinter.py first.")
    drugs, pairs, stats = parse_files(files)
    write_jsonl(args.out_dir / "ddinter_drugs.jsonl", drugs)
    write_jsonl(args.out_dir / "ddinter_pairs.jsonl", pairs)
    levels = Counter(p["level"] for p in pairs)
    print(f"files: {len(files)}  rows read: {stats['rows']}")
    print(f"drugs: {len(drugs)}  unique pairs: {len(pairs)}")
    print("pairs by level:", dict(levels))
    for key, n in stats.items():
        if key != "rows":
            print(f"  {key}: {n}")


if __name__ == "__main__":
    main()