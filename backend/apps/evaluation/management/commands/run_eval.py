"""Run the evaluation and print n, recall, precision, severity match and the guardrail pass rate (with 95% intervals).

    python manage.py run_eval                                  # = --split dev (safe default while you work)
    python manage.py run_eval --split dev --cases              # + every case with PASS / FAIL
    python manage.py run_eval --split test                     # the number you report (once)
    python manage.py run_eval --brands data/eval/eval_brands.csv --show-errors
    python manage.py run_eval --split test --json data/processed/eval_test.json

Runs inline (no Celery needed) through the same code the API task uses, and records an EvalRun either way; the
dashboard page (/admin/evaluation) shows the latest completed run of each split.
Brand CSV columns: brand_name, expected_generic (a generic name, or "unresolved" / empty for a brand that is NOT in
the mapping), optionally strength, reviewed_by. Use brands that are NOT in the mapping you loaded, otherwise the
answer is a lookup of our own data (the report shows `exact_lookup_share` for that reason).

The default is `dev`, never `test`: the test split is meant to be reported once, so it is only run when you ask for it.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.evaluation import dashboard, metrics, runner, services
from apps.evaluation.models import EvalRun

fmt = metrics.format_rate


class Command(BaseCommand):
    help = "Evaluate detection on the dev/test split and/or brand resolution on a held-out CSV. Prints the numbers."

    def add_arguments(self, parser):
        parser.add_argument("--split", choices=list(services.SPLITS),
                            help="Default: dev (when neither --split nor --brands is given).")
        parser.add_argument("--brands", type=Path, help="Held-out brand CSV (see --help of this command).")
        parser.add_argument("--json", type=Path, dest="json_path", help="Also write the run(s) to this JSON file.")
        parser.add_argument("--show-errors", action="store_true", help="Brand run only: print wrong rows (never stored).")
        parser.add_argument("--cases", action="store_true",
                            help="Dev split only: print every case with PASS / FAIL (the test split never stores them).")

    def handle(self, *args, **opts):
        split = opts["split"] or (None if opts["brands"] else "dev")
        runs = []
        if split:
            runs.append(self._pairs(split, opts["cases"]))
        if opts["brands"]:
            runs.append(self._brands(opts["brands"], opts["show_errors"]))
        if opts["json_path"]:
            payload = [{"id": r.id, "kind": r.kind, "split": r.split, "status": r.status, "n_cases": r.n_cases,
                        "fingerprint": r.fingerprint, "metrics": r.metrics, "config": r.config} for r in runs]
            opts["json_path"].parent.mkdir(parents=True, exist_ok=True)
            opts["json_path"].write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            self.stdout.write(f"written: {opts['json_path']}")

    # ---------------------------------------------------------------------------------------- pairs
    def _pairs(self, split: str, show_cases: bool) -> EvalRun:
        try:
            run = services.start_run(split=split)
        except services.EvalRequestError as exc:
            raise CommandError(f"{exc.detail['code']}: {exc.detail['detail']}") from exc
        if split == "test":
            self.stdout.write(self.style.WARNING(
                "TEST split: this is the number you report. Do not change prompts, thresholds or data because of it."))
        self.stdout.write(f"running evaluation #{run.id} on the {split} split ({run.n_cases} cases)...")
        runner.execute_run(run.id)
        run = EvalRun.objects.get(pk=run.id)
        if run.status != "completed":
            raise CommandError(f"evaluation failed: {run.error_code or run.status}. No metrics were stored.")

        m, out = run.metrics, self.stdout
        out.write(self.style.MIGRATE_HEADING(f"\nDETECTION  split={split}  n={m['n']}  (positives={m['positives']}, negatives={m['negatives']})"))
        out.write(f"  recall     : {fmt(m['recall'])}")
        if m["negatives"] == 0:
            out.write(self.style.WARNING(
                "  precision  : not measurable (no reviewer-labelled negatives: with none, a false alarm cannot occur, "
                "so a bare 100% would be meaningless)"))
        else:
            out.write(f"  precision  : {fmt(m['precision'])}")
        out.write(f"  specificity: {fmt(m['specificity'])}")
        out.write(f"  F1         : {m['f1'] if m['f1'] is not None else 'not measurable'}")
        out.write(f"  severity match among detected: {fmt(m['severity_agreement'])}")
        out.write(f"  under-called: {m['undercalled']}   over-called: {m['overcalled']}   "
                  f"major not called major: {fmt(m['major_not_called_major'])}")
        out.write("  per severity (reviewer label):")
        for sev, info in m["per_severity"].items():
            out.write(f"    {sev:9} n={info['n_expected']:<4} flagged: {fmt(info['detected'])}   exact: {fmt(info['exact'])}")
        out.write("  confusion (rows = reviewer, columns = system):")
        out.write("    " + "".join(f"{p:>10}" for p in metrics.PREDICTED))
        for e in metrics.EXPECTED:
            out.write(f"  {e:>9}" + "".join(f"{m['confusion'][e][p]:>10}" for p in metrics.PREDICTED))
        out.write(f"  missed positives, by reason: {m['missed_by_reason'] or 'none'}")

        # Guardrail: "no finding with a severity is saved without evidence".
        integrity = m["integrity"]
        violations = integrity["severity_without_citation"]
        flag = self.style.SUCCESS("OK") if violations == 0 else self.style.ERROR("VIOLATION")
        out.write(f"  guardrail (this run): {fmt(metrics.rate(m['n'] - violations, m['n']))} of predictions obey "
                  f"'no severity without citation'; violations = {violations} (must be 0) {flag}")
        out.write(f"    no-record pairs = {integrity['pairs_with_no_record']}, reported unknown = {integrity['no_record_reported_unknown']}")
        audit = dashboard.guardrail_audit()
        audit_flag = self.style.SUCCESS("OK") if audit["severity_without_evidence"] == 0 else self.style.ERROR("VIOLATION")
        out.write(f"  guardrail (saved findings): {audit['severity_without_evidence']} of {audit['findings_with_severity']} "
                  f"findings with a severity have no evidence (must be 0) {audit_flag}")

        for caveat in m["caveats"]:
            out.write(self.style.WARNING(f"  caveat: {caveat}"))
        n_circular = run.config.get("n_circular_reference", 0)
        if n_circular:
            out.write(self.style.WARNING(
                f"  caveat: {n_circular} of {m['n']} labels come from DDInter/openFDA (the system's own sources). These numbers "
                "show fidelity to the source, not clinical accuracy."))
        if run.config.get("test_note"):
            out.write(self.style.WARNING(f"  {run.config['test_note']}"))

        if split == "dev":
            results = m.get("case_results") or []
            if show_cases and results:
                out.write("  cases:")
                for r in results:
                    mark = self.style.SUCCESS("PASS") if r["passed"] else self.style.ERROR("FAIL")
                    out.write(f"    {mark}  {r['drug_a']} + {r['drug_b']}: reviewer={r['expected']} "
                              f"system={r['predicted']} ({r['outcome']})")
            elif m.get("case_details"):
                out.write("  dev disagreements:")
                for d in m["case_details"]:
                    out.write(f"    {d['drug_a']} + {d['drug_b']}: reviewer={d['expected']} system={d['predicted']} ({d['pair_status']})")
        out.write(f"  transport: {', '.join(run.config.get('transports', [])) or 'n/a'}   fingerprint: {run.fingerprint[:12]}")
        return run

    # ---------------------------------------------------------------------------------------- brands
    def _brands(self, path: Path, show_errors: bool) -> EvalRun:
        try:
            rows = list(services.read_csv_rows(path, services.EVAL_BRAND_COLUMNS))
            run, errors = services.run_brand_eval(rows)
        except FileNotFoundError as exc:
            raise CommandError(f"Input not found: {exc}") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except services.EvalRequestError as exc:
            raise CommandError(f"{exc.detail['code']}: {exc.detail['detail']}") from exc

        m, out = run.metrics, self.stdout
        out.write(self.style.MIGRATE_HEADING(f"\nBRAND RESOLUTION  n={m['n']}  (known={m['known_n']}, should stay unresolved={m['unresolvable_n']})"))
        out.write(f"  accuracy             : {fmt(m['accuracy'])}")
        out.write(f"  precision when resolved: {fmt(m['resolved_precision'])}")
        out.write(f"  coverage of known    : {fmt(m['coverage_of_known'])}")
        out.write(f"  wrong silent matches : {fmt(m['wrong_resolution_rate'])}   (must stay as close to 0 as possible)")
        out.write(f"  correct={m['correct_resolved']} wrong={m['wrong_resolution']} missed={m['missed']} correct-abstention={m['correct_abstention']}")
        out.write(f"  by match type: {m['by_match_type'] or 'none'}   exact lookups: {fmt(m['exact_lookup_share'])}")
        for caveat in run.config["caveats"]:
            out.write(self.style.WARNING(f"  caveat: {caveat}"))
        if show_errors:
            out.write("  wrong rows (console only, not stored; do not tune the mapping on the held-out list):")
            for e in errors:
                out.write(f"    line {e['line']}: {e['brand']} expected={e['expected']} got={e['got']} ({e['reason']})")
        out.write(f"  fingerprint: {run.fingerprint[:12]}")
        return run
