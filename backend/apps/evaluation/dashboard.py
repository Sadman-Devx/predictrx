"""Read model for the evaluation dashboard (GET /api/eval/dashboard/).

It only READS recorded `EvalRun` rows and saved `RiskFinding` rows. It never computes a number of its own that is not
backed by a run, so the page cannot show a figure nobody measured (docs/rule.md §1).

Honesty rules built in:
  * precision is reported as "not measurable" when the set has no reviewer-labelled negatives ('none'). With no
    negatives there can be no false positive, so a bare 100% would be an artefact, not a result;
  * labels that name DDInter / openFDA are counted and flagged: they check that the pipeline reproduces its own source,
    not that it is clinically right;
  * per-case rows exist for the dev split only (the test split stays count-only, see runner.py).
"""
from django.utils import timezone

from apps.analysis.models import RiskFinding

from . import metrics, services
from .models import EvalRun

HISTORY_LIMIT = 10


def guardrail_audit() -> dict:
    """Live check of everything saved so far: is there a finding with a severity but no evidence? Must be 0.

    `RiskFinding.save()` refuses such a row; this catches anything written around it (bulk_create, raw SQL, a bad
    migration). pass_rate is over findings that carry a severity (those are the ones the rule applies to).
    """
    findings = RiskFinding.objects.all()
    with_severity = findings.exclude(severity="unknown")
    n_severity = with_severity.count()
    violations = with_severity.filter(evidence=[]).count()
    return {
        "findings_total": findings.count(),
        "findings_with_severity": n_severity,
        "severity_without_evidence": violations,
        "pass_rate": metrics.rate(n_severity - violations, n_severity),
    }


def _latest_completed(split: str):
    return EvalRun.objects.filter(kind="pairs", split=split, status="completed").order_by("-id").first()


def _run_block(run, split: str):
    if run is None:
        return None
    m = run.metrics or {}
    cfg = run.config or {}
    n = run.n_cases
    negatives = int(m.get("negatives", 0))
    violations = int((m.get("integrity") or {}).get("severity_without_citation", 0))
    n_circular = int(cfg.get("n_circular_reference", 0))

    caveats = list(m.get("caveats") or [])
    if n_circular:
        caveats.append(
            f"{n_circular} of {n} labels come from DDInter/openFDA, the data this system retrieves from. These "
            "numbers show that the pipeline reproduces its own source faithfully; they do not measure clinical "
            "accuracy. Use reviewer-labelled cases from an independent source for that.")
    if cfg.get("test_note"):
        caveats.append(cfg["test_note"])
    if cfg.get("n_unreviewed"):
        caveats.append(f"{cfg['n_unreviewed']} case(s) have no reviewer name.")

    return {
        "run_id": run.id,
        "split": split,
        "finished_at": run.finished_at,
        "n_cases": n,
        "fingerprint": (run.fingerprint or "")[:12],
        "positives": m.get("positives", 0),
        "negatives": negatives,
        "recall": m.get("recall"),
        "precision": m.get("precision"),
        "precision_measurable": negatives > 0,  # False -> show "not measurable", never the bare number
        "specificity": m.get("specificity"),
        "severity_agreement": m.get("severity_agreement"),
        "major_not_called_major": m.get("major_not_called_major"),
        "tp": m.get("tp", 0), "fp": m.get("fp", 0), "fn": m.get("fn", 0), "tn": m.get("tn", 0),
        "undercalled": m.get("undercalled", 0),
        "overcalled": m.get("overcalled", 0),
        "per_severity": m.get("per_severity", {}),
        "confusion": m.get("confusion", {}),
        "missed_by_reason": m.get("missed_by_reason", {}),
        "guardrail": {  # this run's predictions: how many carried a severity without a citation
            "checked": n,
            "violations": violations,
            "pass_rate": metrics.rate(n - violations, n),
        },
        "reference_labels_from_source": n_circular,
        "caveats": caveats,
        "cases": m.get("case_results") if split == "dev" else None,
        "cases_hidden": split == "test",
        "transports": cfg.get("transports", []),
    }


def _history() -> list:
    out = []
    for run in EvalRun.objects.filter(kind="pairs").order_by("-id")[:HISTORY_LIMIT]:
        m = run.metrics or {}
        done = run.status == "completed"
        recall = (m.get("recall") or {}).get("value") if done else None
        precision = (m.get("precision") or {}).get("value") if done and m.get("negatives", 0) > 0 else None
        agreement = (m.get("severity_agreement") or {}).get("value") if done else None
        out.append({"id": run.id, "split": run.split, "status": run.status, "error_code": run.error_code,
                    "n_cases": run.n_cases, "recall": recall, "precision": precision,
                    "severity_agreement": agreement, "finished_at": run.finished_at})
    return out


def build_dashboard() -> dict:
    return {
        "generated_at": timezone.now(),
        "pairs": {split: _run_block(_latest_completed(split), split) for split in services.SPLITS},
        "set": services.describe_set(),
        "guardrail_audit": guardrail_audit(),
        "history": _history(),
    }
