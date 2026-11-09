"""Stage 2 — PARSE: turn raw openFDA label JSON into flat documents with named sections.

Input : data/raw/openfda/*.json        Output: data/processed/openfda_parsed.jsonl
Only the sections the product needs are kept. A label that lacks a field simply has no such section.
"""
import argparse
import json
import re
from pathlib import Path

from common import PROCESSED_DIR, RAW_DIR, write_jsonl

# openFDA field name -> section title used in the knowledge base
SECTIONS = {
    "boxed_warning": "BOXED WARNING",
    "contraindications": "CONTRAINDICATIONS",
    "warnings": "WARNINGS",
    "warnings_and_cautions": "WARNINGS AND CAUTIONS",
    "precautions": "PRECAUTIONS",
    "drug_interactions": "DRUG INTERACTIONS",
    "indications_and_usage": "INDICATIONS AND USAGE",
}


def as_text(value) -> str:
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_result(result: dict, *, query_name: str, aliases: list[str], fetched_at: str) -> dict:
    openfda = result.get("openfda") or {}
    sections = {}
    for field, title in SECTIONS.items():
        text = as_text(result.get(field))
        if text:
            sections[title] = text
    set_id = result.get("set_id", "")
    return {
        "query_name": query_name,
        "aliases": aliases,
        "label_id": result.get("id", ""),
        "set_id": set_id,
        "version": str(result.get("version", "")),
        "effective_time": str(result.get("effective_time", "")),
        "generic_names": [as_text(g) for g in (openfda.get("generic_name") or [])],
        "brand_names": [as_text(b) for b in (openfda.get("brand_name") or [])],
        "source_url": f'https://api.fda.gov/drug/label.json?search=set_id:"{set_id}"' if set_id else "",
        "fetched_at": fetched_at,
        "sections": sections,
    }


def parse_file(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        parse_result(r, query_name=payload["query_name"], aliases=payload.get("aliases", []),
                     fetched_at=payload.get("fetched_at", ""))
        for r in payload.get("results", [])
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, default=RAW_DIR / "openfda")
    ap.add_argument("--out", type=Path, default=PROCESSED_DIR / "openfda_parsed.jsonl")
    args = ap.parse_args()

    docs = []
    files = sorted(args.raw_dir.glob("*.json"))
    for f in files:
        docs.extend(parse_file(f))
    write_jsonl(args.out, docs)
    with_ix = sum(1 for d in docs if "DRUG INTERACTIONS" in d["sections"])
    print(f"parsed {len(files)} files -> {len(docs)} labels ({with_ix} with a DRUG INTERACTIONS section) -> {args.out}")


if __name__ == "__main__":
    main()