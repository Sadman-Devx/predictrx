"""Build a candidate evaluation sheet from the licensed dataset already loaded in the database (DDInter 2.0).

    python manage.py build_eval_set                          # review sheet: labels left blank for a reviewer
    python manage.py build_eval_set --positives 30 --negatives 15
    python manage.py build_eval_set --prefill-reference      # fidelity baseline: DDInter's own labels, dev only

Nothing is typed in by hand: every positive pair is sampled (seeded, so reproducible) from `Interaction` rows loaded
from DDInter (data/SOURCES.md). Output CSV matches `load_eval_cases`, plus helper columns (reference_severity,
reference_source, note) that the loader ignores.

What the two modes mean (read this before quoting a number):

  default            expected_severity / rationale_ref / reviewed_by are BLANK. DDInter's label is shown in
                     `reference_severity` only as a hint. A pharmacist / mentor confirms or changes it using an
                     INDEPENDENT source and fills the three columns. Only then does the loader accept the row, and
                     only then can it go to the `test` split. This is the set whose numbers you can defend.

  --prefill-reference  expected_severity = DDInter's own severity. The system retrieves from DDInter, so it will
                     reproduce these labels almost perfectly: a high number here shows the pipeline is faithful to
                     its source, NOT that it is clinically accurate (docs/rule.md §2, backend-design §8). The loader
                     accepts such rows only with `--allow-circular-dev` and forces them into `dev`.
                     A pair loaded this way is used up: it cannot later be re-labelled for `test`.

Negatives ('none') can never be prefilled: "no DDInter record" is not evidence of "no interaction" (DDInter's own
disclaimer). They are listed unlabelled for the reviewer, so precision becomes measurable only after a human labels them.

The output is derived from DDInter (CC BY-NC-SA 4.0). Keep it under data/processed/ (git-ignored); do not commit it.
"""
import csv
import random
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.drugs.models import Drug, Interaction
from apps.evaluation import metrics, services
from apps.evaluation.models import EvalCase

SOURCE = "ddinter"
SOURCE_LABEL = "DDInter 2.0"
DEFAULT_SEED = "predictrx-evalset-v1"
MIN_RECORDS_FOR_NEGATIVE = 3  # only well-covered drugs are used for negative candidates
COLUMNS = ["drug_a", "drug_b", "expected_severity", "rationale_ref", "reviewed_by", "split",
           "reference_severity", "reference_source", "note"]

NOTE_POSITIVE = ("Reviewer: confirm or change the severity using an INDEPENDENT source (not DDInter/openFDA), "
                 "then fill expected_severity, rationale_ref and reviewed_by.")
NOTE_NEGATIVE = ("No DDInter record. Absence of a record is NOT evidence of no interaction. Reviewer: label "
                 "'none' (or a severity) from an independent source, or delete the row.")
NOTE_PREFILLED = ("Prefilled from the DDInter record itself: pipeline-fidelity check only (same-source), "
                  "not clinical validation.")


def allocate(total: int, available: dict) -> dict:
    """Split `total` evenly across the severity pools; a pool that is too small hands its unused share to the others.

    allocate(30, {"major": 100, "moderate": 100, "minor": 4}) -> {"major": 13, "moderate": 13, "minor": 4}
    """
    quota = {key: 0 for key in available}
    remaining = total
    open_keys = [key for key, size in available.items() if size > 0]
    while remaining > 0 and open_keys:
        share = max(1, remaining // len(open_keys))
        progressed = False
        for key in list(open_keys):
            take = min(share, available[key] - quota[key], remaining)
            if take > 0:
                quota[key] += take
                remaining -= take
                progressed = True
            if quota[key] >= available[key]:
                open_keys.remove(key)
            if remaining == 0:
                break
        if not progressed:
            break
    return quota


class Command(BaseCommand):
    help = "Sample a candidate eval sheet (CSV) from the loaded DDInter interactions. No labels are invented."

    def add_arguments(self, parser):
        parser.add_argument("--positives", type=int, default=30, help="Pairs that DDInter lists (default 30).")
        parser.add_argument("--negatives", type=int, default=15,
                            help="Pairs with no DDInter record, left unlabelled for a reviewer (default 15).")
        parser.add_argument("--seed", default=DEFAULT_SEED, help="Same seed + same data = same sheet.")
        parser.add_argument("--out", type=Path, default=None,
                            help="Output CSV (default: <repo>/data/processed/eval_candidates.csv, git-ignored).")
        parser.add_argument("--prefill-reference", action="store_true",
                            help="Fill positives with DDInter's own severity (same-source baseline, dev only).")

    def handle(self, *args, **opts):
        n_pos, n_neg = opts["positives"], opts["negatives"]
        if n_pos < 0 or n_neg < 0 or n_pos + n_neg == 0:
            raise CommandError("--positives and --negatives must be >= 0 and not both zero.")

        out_path = opts["out"] or (settings.REPO_ROOT / "data" / "processed" / "eval_candidates.csv")
        rng = random.Random(opts["seed"])
        taken = set(EvalCase.objects.values_list("drug_a_id", "drug_b_id"))

        rows = []
        positives = self._positives(n_pos, rng, taken, opts["prefill_reference"])
        rows.extend(positives)
        negatives = self._negatives(n_neg, rng, taken)
        rows.extend(negatives)
        if not rows:
            raise CommandError("Nothing to write.")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        out = self.stdout
        by_sev = Counter(r["reference_severity"] for r in positives)
        out.write(f"written: {out_path}")
        out.write(f"  positives: {len(positives)}  by DDInter severity: {dict(by_sev)}")
        out.write(f"  negatives: {len(negatives)}  (unlabelled: a reviewer must label them)")
        if len(positives) < n_pos:
            out.write(self.style.WARNING(f"  only {len(positives)} of {n_pos} requested positives were available."))
        if len(negatives) < n_neg:
            out.write(self.style.WARNING(f"  only {len(negatives)} of {n_neg} requested negatives could be drawn."))
        if opts["prefill_reference"]:
            out.write(self.style.WARNING(
                "  MODE prefill-reference: labels are DDInter's own. Load with --allow-circular-dev (forced to dev). "
                "High numbers here mean 'faithful to the source', not 'clinically accurate'."))
        else:
            out.write("  MODE review sheet: expected_severity / rationale_ref / reviewed_by are blank on purpose. "
                      "Give the sheet to a pharmacist or mentor; load it only after those columns are filled.")
        out.write(self.style.WARNING(
            "  This file is derived from DDInter (CC BY-NC-SA 4.0). Keep it in data/processed/ (git-ignored); do not commit it."))
        out.write("next: python manage.py load_eval_cases --path <file> --dry-run"
                  + (" --allow-circular-dev" if opts["prefill_reference"] else ""))

    # ---------------------------------------------------------------------------------------- positives
    def _positives(self, total: int, rng: random.Random, taken: set, prefill: bool) -> list:
        if total == 0:
            return []
        records = Interaction.objects.filter(source=SOURCE, severity__in=metrics.POSITIVE).values_list(
            "drug_a_id", "drug_b_id", "severity", "source_ref", "drug_a__generic_name", "drug_b__generic_name")
        pools: dict = {sev: [] for sev in metrics.POSITIVE}
        for a_id, b_id, severity, source_ref, name_a, name_b in records.iterator(chunk_size=2000):
            if (a_id, b_id) in taken:
                continue
            pools[severity].append((name_a, name_b, severity, (source_ref or "").strip()[:60]))
        if not any(pools.values()):
            raise CommandError("No DDInter interactions with a severity are loaded (or all are already in the eval "
                               "set). Run the data pipeline first: python data/pipeline/run_all.py")

        quota = allocate(total, {sev: len(pool) for sev, pool in pools.items()})
        out = []
        for sev in metrics.POSITIVE:
            pool = sorted(pools[sev])  # stable order first, so the seeded shuffle is reproducible
            rng.shuffle(pool)
            for name_a, name_b, severity, source_ref in pool[:quota[sev]]:
                row = {"drug_a": name_a, "drug_b": name_b, "expected_severity": "", "rationale_ref": "",
                       "reviewed_by": "", "split": "", "reference_severity": severity,
                       "reference_source": SOURCE_LABEL, "note": NOTE_POSITIVE}
                if prefill:
                    ref = f" ({source_ref})" if source_ref else ""
                    row.update(expected_severity=severity, split="dev", note=NOTE_PREFILLED,
                               rationale_ref=f"{SOURCE_LABEL} record{ref}; same-source label for a pipeline-fidelity "
                                             "check, not independent validation.",
                               reviewed_by=f"{SOURCE_LABEL} dataset")
                out.append(row)
        out.sort(key=lambda r: (r["drug_a"], r["drug_b"]))
        return out

    # ---------------------------------------------------------------------------------------- negatives
    def _negatives(self, total: int, rng: random.Random, taken: set) -> list:
        if total == 0:
            return []
        every_pair, per_drug = set(), Counter()
        for a_id, b_id in Interaction.objects.values_list("drug_a_id", "drug_b_id").iterator(chunk_size=5000):
            every_pair.add((a_id, b_id))  # any source: a pair known anywhere is not a negative candidate
            per_drug[a_id] += 1
            per_drug[b_id] += 1
        covered = sorted(d for d, n in per_drug.items() if n >= MIN_RECORDS_FOR_NEGATIVE)
        if len(covered) < 2:
            return []

        chosen, attempts = [], 0
        while len(chosen) < total and attempts < total * 200:
            attempts += 1
            a_id, b_id = Interaction.canonical(*rng.sample(covered, 2))
            pair = (a_id, b_id)
            if pair in every_pair or pair in taken or pair in chosen:
                continue
            chosen.append(pair)

        names = Drug.objects.in_bulk({i for pair in chosen for i in pair})
        out = []
        for a_id, b_id in chosen:
            out.append({"drug_a": names[a_id].generic_name, "drug_b": names[b_id].generic_name,
                        "expected_severity": "", "rationale_ref": "", "reviewed_by": "", "split": "",
                        "reference_severity": "(no DDInter record)", "reference_source": SOURCE_LABEL,
                        "note": NOTE_NEGATIVE})
        out.sort(key=lambda r: (r["drug_a"], r["drug_b"]))
        return out
