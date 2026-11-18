from datetime import timedelta

import pytest
from django.utils import timezone

from apps.analysis.models import AnalysisRun
from apps.clinical.models import PrescriptionScan
from apps.notifications.models import Notification
from apps.notifications.services import record_analysis_notification, record_scan_notification
from apps.patients.models import Patient


def _scan(patient, status):
    return PrescriptionScan.objects.create(
        patient=patient,
        image="",
        status=status,
        retain_until=timezone.now() + timedelta(days=1),
    )


@pytest.mark.django_db
def test_notification_tasks_record_terminal_events_once(monkeypatch, doctor):
    patient = Patient.objects.create(owner=doctor, patient_code="PX-NOTIFY")
    ready_scan = _scan(patient, "extracted")
    failed_scan = _scan(patient, "failed")
    completed_run = AnalysisRun.objects.create(
        patient=patient,
        idempotency_key="notification-analysis-completed",
        status="completed",
    )
    failed_run = AnalysisRun.objects.create(
        patient=patient,
        idempotency_key="notification-analysis-failed",
        status="failed",
    )

    monkeypatch.setattr(
        "apps.clinical.tasks.runner.execute_scan",
        lambda scan_id: "extracted" if scan_id == ready_scan.id else "failed",
    )
    monkeypatch.setattr(
        "apps.analysis.tasks.runner.execute_run",
        lambda run_id: "completed" if run_id == completed_run.id else "failed",
    )

    from apps.analysis.tasks import run_analysis
    from apps.clinical.tasks import extract_prescription

    assert extract_prescription.run(ready_scan.id) == "extracted"
    assert extract_prescription.run(failed_scan.id) == "failed"
    assert run_analysis.run(completed_run.id) == "completed"
    assert run_analysis.run(failed_run.id) == "failed"
    assert extract_prescription.run(ready_scan.id) == "extracted"
    assert run_analysis.run(completed_run.id) == "completed"

    assert Notification.objects.filter(recipient=doctor).count() == 4
    assert Notification.objects.get(scan=ready_scan).event == "scan_ready"
    assert Notification.objects.get(scan=failed_scan).event == "scan_failed"
    assert Notification.objects.get(analysis_run=completed_run).event == "analysis_ready"
    assert Notification.objects.get(analysis_run=failed_run).event == "analysis_failed"


@pytest.mark.django_db
def test_notification_api_is_owner_scoped_and_marks_items_read(
    api_client, auth_client, doctor, other_doctor, make_user
):
    patient = Patient.objects.create(owner=doctor, patient_code="PX-NOTIFY-OWN")
    other_patient = Patient.objects.create(owner=other_doctor, patient_code="PX-NOTIFY-OTHER")
    own = record_scan_notification(_scan(patient, "extracted"))
    other = record_scan_notification(_scan(other_patient, "failed"))

    response = auth_client(doctor).get("/api/notifications/")

    assert response.status_code == 200
    body = response.json()
    assert body["unread_count"] == 1
    assert len(body["results"]) == 1
    assert body["results"][0]["id"] == own.id
    assert body["results"][0]["event"] == "scan_ready"
    assert body["results"][0]["patient_id"] == patient.id
    assert "medications" not in body["results"][0]
    assert response["Cache-Control"] == "private, no-store"

    read_response = auth_client(doctor).post(f"/api/notifications/{own.id}/read/", {}, format="json")
    assert read_response.status_code == 200
    assert read_response.json()["read_at"] is not None
    assert auth_client(doctor).get("/api/notifications/").json()["unread_count"] == 0
    assert auth_client(doctor).post(f"/api/notifications/{other.id}/read/", {}, format="json").status_code == 404

    family_client = auth_client(make_user("family"))
    assert family_client.get("/api/notifications/").status_code == 403
    assert api_client.get("/api/notifications/").status_code == 401


@pytest.mark.django_db
def test_notification_creation_is_idempotent_and_ignores_nonterminal_status(doctor):
    patient = Patient.objects.create(owner=doctor, patient_code="PX-NOTIFY-STATE")
    queued_scan = _scan(patient, "queued")
    failed_scan = _scan(patient, "failed")

    assert record_scan_notification(queued_scan) is None
    first = record_scan_notification(failed_scan)
    second = record_scan_notification(failed_scan)

    assert first is not None
    assert second == first
    assert Notification.objects.filter(recipient=doctor).count() == 1


@pytest.mark.django_db
def test_stuck_scan_failure_creates_a_notification(doctor, settings):
    settings.SCAN_STUCK_MINUTES = 1
    patient = Patient.objects.create(owner=doctor, patient_code="PX-NOTIFY-STUCK")
    scan = _scan(patient, "processing")
    PrescriptionScan.objects.filter(pk=scan.pk).update(created_at=timezone.now() - timedelta(minutes=2))

    from apps.clinical.tasks import fail_stuck_scans

    assert fail_stuck_scans.run() == 1

    scan.refresh_from_db()
    assert scan.status == "failed"
    assert Notification.objects.get(scan=scan).event == "scan_failed"
