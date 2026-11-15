"""Load the reviewer-labelled drug pairs into EvalCase and assign the dev/test split.

    python manage.py load_eval_cases --path data/eval/eval_cases.csv --dry-run
    python manage.py load_eval_cases --path data/eval/eval_cases.csv

CSV columns (header row required): drug_a, drug_b, expected_severity (none|minor|moderate|major), rationale_ref,
and optionally reviewed_by, split (dev|test). Use GENERIC names.

Rules (docs/rule.md §2, backend-design §8):
  * every label needs an independent source note (rationale_ref) and a reviewer;
  * a row that names DDInter or openFDA as its source is refused (circular: the system retrieves from them);
  * the split is assigned by a stable hash of the pair unless the file gives one; existing cases are NEVER
    re-labelled or moved, so re-running the load cannot shuffle pairs between dev and test;
  * every refused row is listed with a reason. Nothing is dropped silently.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.evaluation import services


class Command(BaseCommand):
    help = "Load reviewer-labelled drug pairs (CSV) into EvalCase with a stable dev/test split."

    def add_arguments(self, parser):
        parser.add_argument("--path", type=Path, required=True)
        parser.add_argument("--test-fraction", type=float, default=services.DEFAULT_TEST_FRACTION)
        parser.add_argument("--seed", default=services.DEFAULT_SEED, help="Changing it changes the split of NEW cases.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--allow-unreviewed", action="store_true", help="Accept rows without reviewed_by (dev work only).")
        parser.add_argument("--allow-circular-dev", action="store_true",
                            help="Accept rows sourced from DDInter/openFDA, forced into the dev split (never test).")
        parser.add_argument("--create-missing-drugs", action="store_true",
                            help="Create Drug rows for generic names the database does not know. Review them afterwards.")

    def handle(self, *args, **opts):
        if not 0.0 < opts["test_fraction"] < 1.0:
            raise CommandError("--test-fraction must be between 0 and 1 (exclusive).")
        try:
            rows = list(services.read_csv_rows(opts["path"], services.EVAL_CASE_COLUMNS))
        except FileNotFoundError as exc:
            raise CommandError(f"Input not found: {exc}") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        report = services.load_eval_cases(
            rows, test_fraction=opts["test_fraction"], seed=opts["seed"], dry_run=opts["dry_run"],
            allow_unreviewed=opts["allow_unreviewed"], allow_circular_dev=opts["allow_circular_dev"],
            create_missing_drugs=opts["create_missing_drugs"])

        out = self.stdout
        out.write(f"eval cases: {'DRY RUN (nothing written)' if report.dry_run else 'committed'}")
        out.write(f"  rows read : {report.rows_read}")
        out.write(f"  created   : {report.created}  (dev={report.created_by_split.get('dev', 0)}, "
                  f"test={report.created_by_split.get('test', 0)})")
        out.write(f"  skipped   : {report.skipped_total}")
        for reason, count in report.skipped.most_common():
            lines = ", ".join(str(n) for n in report.skipped_lines.get(reason, []))
            out.write(f"    - {reason}: {count}  (lines {lines}{', ...' if count > len(report.skipped_lines.get(reason, [])) else ''})")
        for name in report.created_drugs:
            out.write(f"  drug      : {name}")
        for note in report.notes:
            out.write(self.style.WARNING(f"  note      : {note}"))

        if not report.dry_run:
            described = services.describe_set()
            out.write("set now in the database:")
            for split in services.SPLITS:
                info = described[split]
                out.write(f"  {split}: n={info['n']}  by label={info['by_expected_severity']}  unreviewed={info['unreviewed']}")
            for warning in described["warnings"]:
                out.write(self.style.WARNING(f"  warning   : {warning}"))
        if report.skipped_total:
            out.write("Skipped rows were NOT loaded. Fix the file and re-run (safe to repeat: loaded cases are never changed).")