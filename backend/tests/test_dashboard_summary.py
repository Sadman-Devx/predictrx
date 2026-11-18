from datetime import timedelta

import pytest
from django.utils import timezone

from apps.analysis.models import AnalysisRun
from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.clinical.models import Medication, PrescriptionScan
from apps.followups.models import FollowUpTask
from apps.patients.models import Patient


def _patient(owner, code):
    return Patient.objects.create(owner=owner, patient_code=code)


def _scan(patient, status="extracted"):
    return PrescriptionScan.objects.create(
        patient=patient,
        image="",
        status=status,
        retain_until=timezone.now() + timedelta(days=1),
    )


def _scanned_medication(patient, scan, *, confirmed=False):
    return Medication.objects.create(
        patient=patient,
        scan=scan,
        raw_text="test medicine",
        source="scan",
        confirmed_by_user=confirmed,
    )


@pytest.mark.django_db
def test_dashboard_summary_is_owner_scoped_and_counts_pending_scans(
    api_client, auth_client, doctor, other_doctor, make_user
):
    family_user = make_user("family")
    patient_a = _patient(doctor, "PX-DASH-A")
    patient_b = _patient(doctor, "PX-DASH-B")
    other_patient = _patient(other_doctor, "PX-DASH-X")

    AnalysisRun.objects.create(patient=patient_a, idempotency_key="dashboard-own-run")
    AnalysisRun.objects.create(patient=other_patient, idempotency_key="dashboard-other-run")

    extracted = _scan(patient_a)
    _scanned_medication(patient_a, extracted)
    _scanned_medication(patient_a, extracted)
    _scanned_medication(patient_a, extracted, confirmed=True)
    Medication.objects.create(patient=patient_a, raw_text="manual medicine", source="manual")
    _scanned_medication(patient_b, _scan(patient_b))
    _scanned_medication(patient_a, _scan(patient_a, status="processing"))
    _scanned_medication(other_patient, _scan(other_patient))

    AuditLog.objects.create(actor=doctor, action=audit.ANALYSIS_START, patient=patient_a)
    AuditLog.objects.create(actor=family_user, action=audit.FAMILY_VIEW, patient=patient_a)
    AuditLog.objects.create(actor=other_doctor, action=audit.PATIENT_READ, patient=other_patient)

    response = auth_client(doctor).get("/api/dashboard/summary/")

    assert response.status_code == 200
    body = response.json()
    assert body["total_patients"] == 2
    assert body["total_analyses"] == 1
    assert body["pending_reviews"] == 2
    assert [patient["id"] for patient in body["recent_patients"]] == [patient_b.id, patient_a.id]
    assert body["recent_patients"][1] == {
        "id": patient_a.id,
        "patient_code": patient_a.patient_code,
        "medication_count": 5,
    }
    assert [item["event"] for item in body["recent_activity"]] == ["family_viewed", "analysis_run"]
    assert {item["patient_code"] for item in body["recent_activity"]} == {patient_a.patient_code}
    assert all(set(item) == {"id", "event", "patient_code", "at"} for item in body["recent_activity"])
    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
def test_dashboard_summary_requires_a_clinician(api_client, auth_client, make_user):
    assert api_client.get("/api/dashboard/summary/").status_code == 401
    family_client = auth_client(make_user("family"))
    assert family_client.get("/api/dashboard/summary/").status_code == 403


@pytest.mark.django_db
def test_dashboard_summary_counts_only_open_and_overdue_followups(
    auth_client, doctor, other_doctor
):
    patient = _patient(doctor, "PX-FOLLOWUP-DASH")
    other_patient = _patient(other_doctor, "PX-FOLLOWUP-OTHER")
    today = timezone.localdate()
    FollowUpTask.objects.create(patient=patient, task_type="review_analysis", due_date=today - timedelta(days=1))
    FollowUpTask.objects.create(patient=patient, task_type="patient_contact", due_date=today)
    FollowUpTask.objects.create(patient=patient, task_type="follow_up_visit", status="in_progress")
    FollowUpTask.objects.create(patient=patient, task_type="medication_reconciliation", status="done",
                                due_date=today - timedelta(days=2))
    FollowUpTask.objects.create(patient=other_patient, task_type="review_analysis", due_date=today - timedelta(days=1))

    response = auth_client(doctor).get("/api/dashboard/summary/")

    assert response.status_code == 200
    assert response.json()["pending_followups"] == 3
    assert response.json()["overdue_followups"] == 1
