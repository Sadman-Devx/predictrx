"""Start-analysis service: validation, idempotency, frozen input snapshot, enqueue.

Rules enforced here (docs/rule.md):
  * One click = one run: `idempotency_key` is unique; a retry with the same key returns the SAME run.
  * Ownership is derived from the authenticated user, never from client input. A foreign patient is a 404.
  * Human-in-the-loop: every medication must be resolved to a Drug, and scan drafts must be user-confirmed.
  * The snapshot is PII-redacted and frozen: an old run stays explainable after the medication list changes.
  * No LLM call here. The API only creates the run and enqueues a Celery task.
"""
import logging
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from ai.guardrails.pii import redact
from apps.audit import services as audit
from apps.clinical.models import ClinicalNote, LabResult, Medication
from apps.patients.models import Patient

from .models import AnalysisRun

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1
MAX_LABS_IN_SNAPSHOT = 20
MAX_NOTES_IN_SNAPSHOT = 5
MIN_DISTINCT_DRUGS = 2


class AnalysisRequestError(APIException):
    """Client-fixable problem. Shape: {"error": {"code": "bad_request", "message": ..., "details": {"code": <specific>, ...}}}."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"

    def __init__(self, code: str, message: str, *, http_status: int | None = None, **extra):
        super().__init__(detail={"detail": message, "code": code, **extra})
        if http_status:
            self.status_code = http_status


def age_band(birth_year: int | None) -> str | None:
    """Coarse band instead of the exact birth year (less identifying, still clinically useful)."""
    if not birth_year:
        return None
    age = date.today().year - birth_year
    if age < 0:
        return None
    if age < 18:
        return "0-17"
    if age >= 90:
        return "90+"
    return f"{(age // 10) * 10}-{(age // 10) * 10 + 9}"


def _redact_counts(total: dict, counts: dict) -> None:
    for label, n in counts.items():
        total[label] = total.get(label, 0) + n


def build_snapshot(patient: Patient, medications: list[Medication], medication_ids: list[int]) -> dict:
    """Frozen, redacted inputs for the pipeline. Contains no patient name (there is none) and no exact birth year."""
    redaction_counts: dict[str, int] = {}

    def clean(text: str) -> str:
        result = redact(text or "")
        _redact_counts(redaction_counts, result.counts)
        return result.text

    meds = []
    for m in sorted(medications, key=lambda x: x.id):
        meds.append({
            "medication_id": m.id,
            "raw_text": clean(m.raw_text),
            "brand_name": clean(m.brand_name),
            "strength": m.strength,
            "frequency": m.frequency,  # informational only; never used for dosing
            "drug_id": m.drug_id,
            "generic_name": m.drug.generic_name if m.drug_id else None,
            "resolution_status": m.resolution_status,
            "source": m.source,
        })

    labs = [
        {
            "test_name": lab.test_name,
            "value": str(lab.value) if lab.value is not None else None,
            "unit": lab.unit,
            "ref_range": lab.ref_range,
        }
        for lab in LabResult.objects.filter(patient=patient).order_by("-recorded_at")[:MAX_LABS_IN_SNAPSHOT]
    ]
    # `text_redacted` is already redacted at write time; we redact again as defence in depth.
    notes = [
        clean(n.text_redacted)
        for n in ClinicalNote.objects.filter(patient=patient).order_by("-created_at")[:MAX_NOTES_IN_SNAPSHOT]
    ]

    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "medication_ids": medication_ids,
        "drug_ids": sorted({m.drug_id for m in medications if m.drug_id}),
        "medications": meds,
        "patient_context": {
            "age_band": age_band(patient.birth_year),
            "sex": patient.sex or None,
            "weight_kg": float(patient.weight_kg) if patient.weight_kg is not None else None,
            "labs": labs,
            "notes": notes,
        },
        "redaction_counts": redaction_counts,  # label -> count only, never the redacted text
    }


def _validate_medications(patient: Patient, medication_ids: list[int]) -> list[Medication]:
    meds = list(Medication.objects.filter(patient=patient, pk__in=medication_ids).select_related("drug"))

    found = {m.id for m in meds}
    missing = [i for i in medication_ids if i not in found]
    if missing:
        raise AnalysisRequestError("medication_not_found", "Some medications do not belong to this patient.",
                                   medication_ids=missing)

    unresolved = [m.id for m in meds if m.drug_id is None]
    if unresolved:
        raise AnalysisRequestError(
            "unresolved_medications",
            "Resolve or remove unresolved medications before running an analysis.",
            medication_ids=unresolved,
        )

    unconfirmed = [m.id for m in meds if m.source == "scan" and not m.confirmed_by_user]
    if unconfirmed:
        raise AnalysisRequestError(
            "unconfirmed_medications",
            "Medications extracted from a scan must be confirmed by a person before analysis.",
            medication_ids=unconfirmed,
        )

    if len({m.drug_id for m in meds}) < MIN_DISTINCT_DRUGS:
        raise AnalysisRequestError("not_enough_drugs", "At least two different drugs are needed to check interactions.")
    return meds


def _check_replay(run: AnalysisRun, user, patient: Patient, medication_ids: list[int]) -> AnalysisRun:
    """A key may only be re-sent for the SAME request. Anything else is a client bug, not a retry."""
    same = (
        run.requested_by_id == user.id
        and run.patient_id == patient.id
        and (run.input_snapshot or {}).get("medication_ids") == medication_ids
    )
    if not same:
        # Deliberately generic: do not reveal whose run owns the key.
        raise AnalysisRequestError("idempotency_key_conflict",
                                   "This idempotency key was already used for a different request.",
                                   http_status=status.HTTP_409_CONFLICT)
    return run


def _enqueue(run_id: int) -> None:
    """Called after the transaction commits, so the worker can never see a run that does not exist yet."""
    from .tasks import run_analysis

    try:
        run_analysis.delay(run_id)
    except Exception:  # noqa: BLE001 — broker outage (Redis down). Fail visibly instead of leaving a run 'queued' forever.
        logger.exception("could not enqueue analysis run %s", run_id)
        AnalysisRun.objects.filter(pk=run_id, status="queued").update(
            status="failed", finished_at=timezone.now(), model_info={"error": "enqueue_failed"}
        )


def start_analysis(request, *, patient_id: int, medication_ids: list[int], idempotency_key: str) -> tuple[AnalysisRun, bool]:
    """Create (or replay) an analysis run. Returns (run, created). Call inside `transaction.atomic()`."""
    user = request.user
    med_ids = sorted(set(medication_ids))

    patient = Patient.objects.filter(pk=patient_id, owner=user).first()
    if patient is None:
        raise NotFound()  # 404, not 403: existence of other doctors' patients is not leaked

    existing = AnalysisRun.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        run = _check_replay(existing, user, patient, med_ids)
        audit.record(request, audit.ANALYSIS_START, patient=patient, obj=run, replay=True, medications=len(med_ids))
        return run, False

    meds = _validate_medications(patient, med_ids)
    snapshot = build_snapshot(patient, meds, med_ids)

    try:
        with transaction.atomic():  # savepoint: a lost race must not poison the outer transaction
            run = AnalysisRun.objects.create(
                patient=patient,
                requested_by=user,
                idempotency_key=idempotency_key,
                status="queued",
                input_snapshot=snapshot,
                model_info={},
            )
    except IntegrityError:
        # Two requests with the same key raced; the other one won. Return its run.
        run = _check_replay(AnalysisRun.objects.get(idempotency_key=idempotency_key), user, patient, med_ids)
        audit.record(request, audit.ANALYSIS_START, patient=patient, obj=run, replay=True, medications=len(med_ids))
        return run, False

    audit.record(request, audit.ANALYSIS_START, patient=patient, obj=run, replay=False, medications=len(med_ids),
                 redactions=snapshot["redaction_counts"])
    transaction.on_commit(lambda: _enqueue(run.id))
    return run, True