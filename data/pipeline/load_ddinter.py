"""Stage 4 — STORE (DDInter): load drugs and interaction pairs into PostgreSQL.

- Each DDInter entry becomes a Drug. Entries whose name equals a seed drug (or one of its aliases) are merged into
  that seed Drug (e.g. "Salbutamol" -> albuterol), so openFDA labels and DDInter rows point at the SAME drug.
- Formulation variants such as "Diclofenac (topical)" stay SEPARATE drugs; only the plain name maps to the seed drug.
- Interactions: stored once per unordered pair (drug_a.id < drug_b.id), source="ddinter". Severity only; mechanism
  and management stay empty because the download files do not contain them.
- Idempotent: existing (drug_a, drug_b, source) rows are kept. Use --replace to reload from scratch.

Run:  python data/pipeline/load_ddinter.py
"""
import argparse
from pathlib import Path

from common import PROCESSED_DIR, django_setup, read_jsonl, read_seed

SOURCE = "ddinter"
LICENSE_DDINTER = "CC BY-NC-SA 4.0 — non-commercial (DDInter). Incomplete; no record does not mean safe."
BATCH = 5000


def build_name_map(seed: list[dict]) -> dict[str, str]:
    name_map = {}
    for item in seed:
        for n in (item["name"], *item["aliases"]):
            name_map[n.strip().lower()] = item["name"]
    return name_map


def load(drugs: list[dict], pairs: list[dict], *, replace: bool = False) -> dict:
    from django.db import transaction

    from apps.drugs.models import Drug, Interaction

    name_map = build_name_map(read_seed())
    stats = {"drugs_created": 0, "pairs_input": len(pairs), "skipped_same_drug": 0, "interactions_before": 0}

    with transaction.atomic():
        if replace:
            Interaction.objects.filter(source=SOURCE).delete()
        stats["interactions_before"] = Interaction.objects.filter(source=SOURCE).count()

        # ddinter id -> target drug key (lower-case generic name)
        id_to_key, key_aliases, key_ids = {}, {}, {}
        for d in drugs:
            lower = d["name"].strip().lower()
            key = name_map.get(lower, lower)
            id_to_key[d["id"]] = key
            key_ids.setdefault(key, []).append(d["id"])
            if lower != key:
                key_aliases.setdefault(key, set()).add(lower)

        existing = {x.generic_name: x for x in Drug.objects.filter(generic_name__in=list(key_ids))}
        new = [Drug(generic_name=k, aliases=[], external_ids={}) for k in key_ids if k not in existing]
        Drug.objects.bulk_create(new, batch_size=BATCH)
        stats["drugs_created"] = len(new)
        by_key = {x.generic_name: x for x in Drug.objects.filter(generic_name__in=list(key_ids))}

        changed = []
        for key, drug in by_key.items():
            aliases = sorted(set(drug.aliases or []) | key_aliases.get(key, set()))
            ext = dict(drug.external_ids or {})
            ext["ddinter"] = sorted(set(ext.get("ddinter", [])) | set(key_ids[key]))
            if aliases != (drug.aliases or []) or ext != (drug.external_ids or {}):
                drug.aliases, drug.external_ids = aliases, ext
                changed.append(drug)
        Drug.objects.bulk_update(changed, ["aliases", "external_ids"], batch_size=BATCH)

        rows = []
        for p in pairs:
            da, db = by_key[id_to_key[p["id_a"]]], by_key[id_to_key[p["id_b"]]]
            if da.id == db.id:
                stats["skipped_same_drug"] += 1
                continue
            lo, hi = (da, db) if da.id < db.id else (db, da)
            rows.append(Interaction(
                drug_a_id=lo.id, drug_b_id=hi.id, severity=p["level"], mechanism="", management="",
                source=SOURCE, source_ref=f"{p['id_a']}|{p['id_b']}", license_note=LICENSE_DDINTER,
            ))
        Interaction.objects.bulk_create(rows, batch_size=BATCH, ignore_conflicts=True)

    stats["interactions_after"] = Interaction.objects.filter(source=SOURCE).count()
    stats["interactions_added"] = stats["interactions_after"] - stats["interactions_before"]
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, default=PROCESSED_DIR)
    ap.add_argument("--replace", action="store_true", help="delete existing ddinter interactions first")
    args = ap.parse_args()

    django_setup()
    stats = load(read_jsonl(args.dir / "ddinter_drugs.jsonl"), read_jsonl(args.dir / "ddinter_pairs.jsonl"),
                 replace=args.replace)
    print(f"drugs created: {stats['drugs_created']}")
    print(f"interactions: {stats['interactions_before']} -> {stats['interactions_after']} (+{stats['interactions_added']})")
    if stats["skipped_same_drug"]:
        print(f"skipped (both entries map to the same drug): {stats['skipped_same_drug']}")


if __name__ == "__main__":
    main()