"""Stage 3 — CLEAN: keep single-ingredient labels for the seed drugs, dedupe, add licence notes.

Input : data/processed/openfda_parsed.jsonl      Output: data/processed/openfda_clean.jsonl
Dropped (and counted): combination products, labels for other drugs, labels with no usable section, duplicates.
"""
import argparse
import hashlib
import re
from collections import Counter
from pathlib import Path

from common import LICENSE_OPENFDA, PROCESSED_DIR, read_jsonl, write_jsonl

SALT_WORDS = {
    "hydrochloride", "hcl", "sodium", "potassium", "calcium", "magnesium", "sulfate", "sulphate", "mesylate",
    "maleate", "tartrate", "besylate", "succinate", "phosphate", "acetate", "citrate", "hydrobromide", "bromide",
    "fumarate", "nitrate", "carbonate", "dihydrate", "monohydrate", "anhydrous", "hemihydrate",
}


def normalize_name(name: str) -> str:
    name = re.sub(r"\(.*?\)", " ", name.lower())
    name = re.sub(r"[^a-z0-9 ]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def strip_salt(name: str) -> str:
    """'warfarin sodium' -> 'warfarin'. Falls back to the normalized name if everything would be stripped."""
    norm = normalize_name(name)
    kept = [t for t in norm.split() if t not in SALT_WORDS]
    return " ".join(kept) or norm


def is_single_ingredient_for(seed_name: str, aliases: list[str], generic_names: list[str]) -> bool:
    """True when every generic name on the label reduces to the seed drug (or one of its aliases)."""
    if not generic_names:
        return False
    wanted = {strip_salt(seed_name), *(strip_salt(a) for a in aliases)}
    reduced = {strip_salt(g) for g in generic_names}
    return len(reduced) == 1 and reduced <= wanted


def content_hash(doc: dict) -> str:
    h = hashlib.sha256()
    h.update(doc["query_name"].encode())
    h.update(doc.get("set_id", "").encode())
    h.update(doc.get("version", "").encode())
    for title in sorted(doc["sections"]):
        h.update(title.encode())
        h.update(doc["sections"][title].encode())
    return h.hexdigest()


def clean_docs(docs: list[dict]) -> tuple[list[dict], Counter]:
    dropped: Counter = Counter()
    seen: set[str] = set()
    out: list[dict] = []
    for doc in docs:
        if not is_single_ingredient_for(doc["query_name"], doc.get("aliases", []), doc.get("generic_names", [])):
            dropped["not_single_ingredient_for_seed"] += 1
            continue
        if not doc["sections"]:
            dropped["no_usable_sections"] += 1
            continue
        digest = content_hash(doc)
        if digest in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(digest)
        out.append({**doc, "content_hash": digest, "license_note": LICENSE_OPENFDA,
                    "drug_name": doc["query_name"]})
    return out, dropped


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inp", type=Path, default=PROCESSED_DIR / "openfda_parsed.jsonl")
    ap.add_argument("--out", type=Path, default=PROCESSED_DIR / "openfda_clean.jsonl")
    args = ap.parse_args()

    docs = read_jsonl(args.inp)
    cleaned, dropped = clean_docs(docs)
    write_jsonl(args.out, cleaned)
    print(f"cleaned {len(docs)} -> {len(cleaned)} labels -> {args.out}")
    for reason, n in dropped.most_common():
        print(f"  dropped {n}: {reason}")


if __name__ == "__main__":
    main()