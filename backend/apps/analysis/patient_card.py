"""Plain-Bangla patient card of a COMPLETED analysis run (GET /api/analysis/{id}/patient-card/).

The card text is written by the Advisory agent from the findings only and stored in `RiskSummary.patient_card_bn`.
It is checked AGAIN here, when it is served (rule.md §2: never skip the output guardrail):

  * dosing / stop / start language  -> the text is replaced by the "insufficient evidence" text
  * an un-negated "safe" claim      -> the text is replaced by the "insufficient evidence" text
  * disclaimer missing              -> the current Bangla disclaimer is appended (never silently dropped)

Nothing is cached or invented: a run that is not completed, or has no stored card, is `available: false` with a null
card, so a partial run can never look final. Reading a card is audited by the view.
"""
from django.conf import settings
from rest_framework import serializers

from ai.guardrails.output_checks import (
    DISCLAIMER_BN,
    DISCLAIMER_EN,
    INSUFFICIENT_EVIDENCE_BN,
    claims_safety,
    contains_dosing_language,
)

from . import results
from .models import AnalysisRun, RiskSummary
from .serializers import DisclaimerSerializer


def guard_card(text: str) -> tuple[str, str | None]:
    """(text to serve, reason it was replaced or None)."""
    text = (text or "").strip()
    if not text:
        return "", "empty"
    reason = "dosing_language" if contains_dosing_language(text) else "safety_claim" if claims_safety(text) else None
    if reason:
        return f"{INSUFFICIENT_EVIDENCE_BN}\n\n{DISCLAIMER_BN}", reason
    if DISCLAIMER_BN not in text:
        text = f"{text}\n\n{DISCLAIMER_BN}"
    return text, None


def build_payload(run: AnalysisRun) -> dict:
    """Everything the serializer needs. `run.patient` must already be loaded (see `get_owned_run`)."""
    base = {
        "run_id": run.id,
        "patient_id": run.patient_id,
        "patient_code": run.patient.patient_code,
        "status": run.status,
        "is_final": run.status in results.FINAL_STATUSES,
        "available": False,
        "patient_card_bn": None,
        "generated_at": None,
        "guardrail_replaced": False,
        "guardrail_reason": None,
        "disclaimer_version": settings.DISCLAIMER_VERSION,
        "disclaimer": {"version": settings.DISCLAIMER_VERSION, "text_en": DISCLAIMER_EN, "text_bn": DISCLAIMER_BN},
    }
    if run.status != "completed":
        return base

    summary = RiskSummary.objects.filter(run=run).first()
    if summary is None:
        return base
    text, reason = guard_card(summary.patient_card_bn)
    if not text:
        return base

    base.update(
        available=True,
        patient_card_bn=text,
        generated_at=run.finished_at or run.started_at,
        guardrail_replaced=reason is not None,
        guardrail_reason=reason,
    )
    return base


class PatientCardSerializer(serializers.Serializer):
    """`patient_card_bn` is null unless `available`. It never contains dosing, strengths or stop/start instructions."""

    run_id = serializers.IntegerField()
    patient_id = serializers.IntegerField()
    patient_code = serializers.CharField()
    status = serializers.CharField()
    is_final = serializers.BooleanField()
    available = serializers.BooleanField()
    patient_card_bn = serializers.CharField(allow_null=True)
    generated_at = serializers.DateTimeField(allow_null=True)
    guardrail_replaced = serializers.BooleanField()
    guardrail_reason = serializers.CharField(allow_null=True)
    disclaimer_version = serializers.CharField()
    disclaimer = DisclaimerSerializer()