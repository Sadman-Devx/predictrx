"""Executes one AnalysisRun inside a Celery worker (never inside a request/response cycle).

Life cycle:  queued --claim--> running --persist--> completed
                                   \\--any failure--> failed   (nothing partial is ever stored as final)

Contract with the LangGraph pipeline (ai/graph.py). The final graph state must look like:
    findings:  [{"drug_a_id", "drug_b_id", "severity", "rationale", "confidence", "verification_status",
                 "evidence": [{"type": "interaction"|"chunk", "id": int, "source": str}]}]
    summaries: {"doctor_en", "doctor_bn", "patient_card_bn", ...}
    trace:     [{"agent_name", "step_order", "input_summary", "output_summary", "tool_calls", "latency_ms"}]
    gaps:      [<medication dicts from the snapshot that the resolver could not resolve>]
    violations:[<output guardrail violation codes>]

Safety net (rule.md §1, §2): even if an agent misbehaves, this module will
  * downgrade a finding that has a severity but no evidence to `unknown` ("insufficient evidence"),
  * replace summaries / rationales containing dosing language with the insufficient-evidence text,
  * fail the whole run (not silently drop a finding) if a finding is malformed.
"""
import logging
from decimal import Decimal, InvalidOperation

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ai.guardrails.output_checks import (INSUFFICIENT_EVIDENCE_BN, INSUFFICIENT_EVIDENCE_EN, check_output,
                                         contains_dosing_language)
from ai.guardrails.pii import redact

from .models import AgentTrace, AnalysisRun, RiskFinding, RiskSummary

logger = logging.getLogger(__name__)

RECURSION_LIMIT = 25  # hard cap on LangGraph steps: no unbounded agent loops
SEVERITIES = {"minor", "moderate", "major", "unknown"}
VERIFICATION = {"verified", "unverified", "conflict"}
EVIDENCE_TYPES = {"interaction", "chunk"}
SUMMARY_TEXT_KEYS = ("doctor_en", "doctor_bn", "patient_card_bn")


class PipelineUnavailable(RuntimeError):
    """The AI package (langgraph etc.) is not installed in this worker."""


class MalformedFinding(ValueError):
    """An agent produced a finding we cannot store faithfully. The run fails instead of hiding it."""


# ------------------------------------------------------------------------------------------------ claim / fail
def claim(run_id: int) -> AnalysisRun | None:
    """queued -> running, atomically. A duplicate delivery of the same task finds status != queued and does nothing."""
    with transaction.atomic():
        run = AnalysisRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None or run.status != "queued":
            return None
        run.status = "running"
        run.started_at = timezone.now()
        run.save(update_fields=["status", "started_at"])
        return run


def fail(run_id: int, error: str, **info) -> None:
    run = AnalysisRun.objects.filter(pk=run_id).first()
    base = dict(run.model_info or {}) if run else {}
    AnalysisRun.objects.filter(pk=run_id).update(
        status="failed", finished_at=timezone.now(), model_info={**base, "error": error, **info}
    )


# ------------------------------------------------------------------------------------------------ pipeline call
def _invoke_pipeline(snapshot: dict) -> dict:
    try:
        from ai.graph import build_graph
    except ImportError as exc:  # langgraph / anthropic not installed in this environment
        raise PipelineUnavailable(str(exc)) from exc

    state = {
        "medications": snapshot.get("medications", []),
        "patient_context": snapshot.get("patient_context", {}),
        "trace": [],
    }
    return build_graph().invoke(state, config={"recursion_limit": RECURSION_LIMIT})


# ------------------------------------------------------------------------------------------------ normalise
def _confidence(value) -> Decimal:
    try:
        d = Decimal(str(value if value is not None else 0))
    except InvalidOperation:
        return Decimal("0.00")
    return max(Decimal("0"), min(Decimal("1"), d)).quantize(Decimal("0.01"))


def _clean_evidence(raw) -> list[dict]:
    out = []
    for e in raw or []:
        if isinstance(e, dict) and e.get("type") in EVIDENCE_TYPES and e.get("id") is not None:
            out.append({"type": e["type"], "id": e["id"], "source": str(e.get("source", ""))})
    return out


def normalize_finding(raw: dict, allowed_drug_ids: set[int]) -> dict:
    try:
        a, b = int(raw["drug_a_id"]), int(raw["drug_b_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MalformedFinding("missing or invalid drug ids") from exc
    if a == b or a not in allowed_drug_ids or b not in allowed_drug_ids:
        raise MalformedFinding("finding refers to a drug that is not in the run's snapshot")
    a, b = sorted((a, b))

    severity = raw.get("severity") if raw.get("severity") in SEVERITIES else "unknown"
    verification = raw.get("verification_status") if raw.get("verification_status") in VERIFICATION else "unverified"
    evidence = _clean_evidence(raw.get("evidence"))
    rationale = str(raw.get("rationale") or "")
    confidence = _confidence(raw.get("confidence"))

    if severity != "unknown" and not evidence:
        # Rule: no warning without a source.
        severity, rationale, verification, confidence = "unknown", INSUFFICIENT_EVIDENCE_EN, "unverified", Decimal("0.00")

    if contains_dosing_language(rationale):
        rationale = INSUFFICIENT_EVIDENCE_EN

    return {"drug_a_id": a, "drug_b_id": b, "severity": severity, "rationale": rationale,
            "confidence": confidence, "verification_status": verification, "evidence": evidence}


# ------------------------------------------------------------------------------------------------ persist
@transaction.atomic
def persist_result(run: AnalysisRun, result: dict) -> None:
    allowed = set((run.input_snapshot or {}).get("drug_ids", []))
    findings = [normalize_finding(f, allowed) for f in result.get("findings") or []]

    summaries = dict(result.get("summaries") or {})
    violations = list(result.get("violations") or [])
    text = " ".join(str(summaries.get(k, "")) for k in SUMMARY_TEXT_KEYS)
    # Final guardrail, independent of the Verifier: it runs on what we are about to store.
    final_violations = check_output(summary_text=text, findings=findings)
    if "dosing_language" in final_violations:
        summaries = {**summaries,
                     "doctor_en": INSUFFICIENT_EVIDENCE_EN, "doctor_bn": INSUFFICIENT_EVIDENCE_BN,
                     "patient_card_bn": INSUFFICIENT_EVIDENCE_BN}
    violations = sorted(set(violations) | set(final_violations))

    # One create() per finding on purpose: RiskFinding.save() is the model-level evidence guard
    # and bulk_create() would bypass it.
    for f in findings:
        RiskFinding.objects.create(run=run, drug_a_id=f["drug_a_id"], drug_b_id=f["drug_b_id"],
                                   severity=f["severity"], rationale=f["rationale"], confidence=f["confidence"],
                                   verification_status=f["verification_status"], evidence=f["evidence"])

    trace = sorted(result.get("trace") or [], key=lambda t: t.get("step_order", 0))
    AgentTrace.objects.bulk_create([
        AgentTrace(
            run=run,
            agent_name=str(t.get("agent_name", ""))[:30],
            step_order=int(t.get("step_order", 0)),
            input_summary=redact(str(t.get("input_summary", ""))).text,
            output_summary=redact(str(t.get("output_summary", ""))).text,
            tool_calls=t.get("tool_calls") or [],
            latency_ms=int(t.get("latency_ms", 0)),
        )
        for t in trace
    ])

    RiskSummary.objects.update_or_create(
        run=run,
        defaults={
            "doctor_summary_en": str(summaries.get("doctor_en", "")),
            "doctor_summary_bn": str(summaries.get("doctor_bn", "")),
            "patient_card_bn": str(summaries.get("patient_card_bn", "")),
            "disclaimer_version": settings.DISCLAIMER_VERSION,
        },
    )

    gap_ids = [g.get("medication_id") for g in result.get("gaps") or [] if isinstance(g, dict)]
    run.model_info = {
        **(run.model_info or {}),
        "pipeline": {"engine": "langgraph", "steps": len(trace), "recursion_limit": RECURSION_LIMIT},
        "result_meta": {"findings": len(findings), "gap_medication_ids": gap_ids, "violations": violations},
    }
    run.status = "completed"
    run.finished_at = timezone.now()
    run.save(update_fields=["model_info", "status", "finished_at"])


# ------------------------------------------------------------------------------------------------ entry point
def execute_run(run_id: int) -> str:
    """Run one analysis end to end. Returns the final status, or 'skipped' if another worker already took it."""
    run = claim(run_id)
    if run is None:
        return "skipped"
    try:
        result = _invoke_pipeline(run.input_snapshot)
        persist_result(run, result)
        return "completed"
    except SoftTimeLimitExceeded:
        fail(run_id, "timeout")
    except PipelineUnavailable:
        logger.error("analysis run %s: AI pipeline is not installed in this worker", run_id)
        fail(run_id, "pipeline_unavailable")
    except MalformedFinding:
        logger.exception("analysis run %s: malformed finding", run_id)
        fail(run_id, "malformed_finding")
    except Exception as exc:  # noqa: BLE001 — last resort: a crashed run must end in a clear failed state
        logger.exception("analysis run %s failed", run_id)
        fail(run_id, "pipeline_error", error_type=exc.__class__.__name__)
    return "failed"