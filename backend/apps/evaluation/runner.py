"""Executes one pair-evaluation inside a Celery worker (or inline from `manage.py run_eval`).

Life cycle:  queued --claim--> running --persist--> completed
                                   \\--any failure--> failed (+ error_code; NO metrics are stored)

* A duplicate delivery finds status != queued and returns 'skipped' (no second run on the same row).
* The split is read when the run executes, and the exact cases are fingerprinted, so a result can always be tied
  to the set it was measured on.
* Per-case details (which pairs were missed) are stored for the DEV split only. For the test split only counts are
  stored: a list of missed test pairs invites fixing the data until the test passes, which is tuning on the test set.
* Logs carry the run id and the exception class only.

error_code values: no_cases · tools_unavailable · timeout · eval_failed · enqueue_failed (set when queuing) ·
timeout (stale-run sweep)
"""
import logging
from collections import Counter

from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from . import metrics, services
from .models import EvalCase, EvalRun

logger = logging.getLogger(__name__)

TEST_RERUN_NOTE = ("The test split is meant to be reported once. This is run #{n}. Do not change prompts, "
                   "thresholds or data in response to test results.")


def claim(run_id: int) -> EvalRun | None:
    """queued -> running, atomically (a single UPDATE ... WHERE status='queued')."""
    if not EvalRun.objects.filter(pk=run_id, status="queued").update(status="running", started_at=timezone.now()):
        return None
    return EvalRun.objects.get(pk=run_id)


def fail(run_id: int, code: str) -> None:
    """Never overwrites a run that already completed."""
    EvalRun.objects.filter(pk=run_id).exclude(status="completed").update(
        status="failed", error_code=code, finished_at=timezone.now())


def _integrity(cases: list, predictions: list) -> dict:
    """Checks that must hold whatever the accuracy is."""
    return {
        "severity_without_citation": sum(1 for p in predictions if p.severity != "unknown" and not p.cited),  # must be 0
        "pairs_with_no_record": sum(1 for p in predictions if p.pair_status == "no_record"),
        "no_record_reported_unknown": sum(1 for p in predictions
                                          if p.pair_status == "no_record" and p.severity == "unknown"),
        "record_unreferenced": sum(1 for p in predictions if p.pair_status == "record_unreferenced"),
    }


def _missed_by_reason(cases: list, predictions: list) -> dict:
    """Why positives were not flagged: a coverage gap in the data, or a record with no usable severity."""
    reasons = Counter()
    for case, p in zip(cases, predictions):
        if case.expected_severity in metrics.POSITIVE and p.severity == "unknown":
            reasons[{"no_record": "no_record_in_table",
                     "record": "record_without_severity"}.get(p.pair_status, p.pair_status)] += 1
    return dict(reasons)


def _dev_details(cases: list, predictions: list) -> list:
    out = []
    for case, p in zip(cases, predictions):
        if case.expected_severity == "none" and p.severity == "unknown":
            continue
        if case.expected_severity == p.severity:
            continue
        out.append({"drug_a": case.drug_a.generic_name, "drug_b": case.drug_b.generic_name,
                    "expected": case.expected_severity, "predicted": p.severity, "pair_status": p.pair_status})
        if len(out) >= services.MAX_DEV_DETAILS:
            break
    return out


def execute_run(run_id: int) -> str:
    """Run one evaluation end to end. Returns the final status, or 'skipped' if another worker already took it."""
    run = claim(run_id)
    if run is None:
        return "skipped"
    try:
        cases = list(EvalCase.objects.select_related("drug_a", "drug_b").filter(split=run.split).order_by("id"))
        if not cases:
            fail(run_id, "no_cases")
            return "failed"

        predictions, config = services.predict_cases(cases)
        result = metrics.detection_metrics((c.expected_severity, p.severity) for c, p in zip(cases, predictions))
        result["integrity"] = _integrity(cases, predictions)
        result["missed_by_reason"] = _missed_by_reason(cases, predictions)
        by_severity = {s: sum(1 for c in cases if c.expected_severity == s) for s in metrics.EXPECTED}
        result["caveats"] = services.split_warnings(run.split, len(cases), by_severity)
        if run.split == "dev":
            result["case_details"] = _dev_details(cases, predictions)

        config = {**run.config, **config, "split": run.split, "n_unreviewed": sum(1 for c in cases if not c.reviewed_by)}
        if run.split == "test":
            number = EvalRun.objects.filter(kind="pairs", split="test", status="completed").count() + 1
            config["test_run_number"] = number
            if number > 1:
                config["test_note"] = TEST_RERUN_NOTE.format(n=number)

        run.metrics, run.config, run.fingerprint = result, config, services.case_fingerprint(cases)
        run.n_cases, run.status, run.error_code, run.finished_at = len(cases), "completed", "", timezone.now()
        run.save(update_fields=["metrics", "config", "fingerprint", "n_cases", "status", "error_code", "finished_at"])
        return "completed"
    except SoftTimeLimitExceeded:
        fail(run_id, "timeout")
    except Exception as exc:  # noqa: BLE001 — a crashed run must end in a clear failed state, with no half result
        from ai.mcp_client import ToolCallError  # lazy: the AI package may be absent in light environments

        if isinstance(exc, ToolCallError):
            logger.error("eval run %s: the interaction tools were unavailable", run_id)
            fail(run_id, "tools_unavailable")
        else:
            logger.exception("eval run %s failed (%s)", run_id, exc.__class__.__name__)
            fail(run_id, "eval_failed")
    return "failed"