from datetime import timedelta

import pytest
from django.utils import timezone

from apps.analysis.models import AnalysisRun
from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.followups.models import FollowUpTask
from apps.patients.models import Patient

URL = "/api/follow-ups/"


@pytest.mark.django_db
class TestFollowUpAccess:
    def test_owner_can_create_list_and_update_audited_tasks(self, doctor, auth_client):
        patient = Patient.objects.create(owner=doctor, patient_code="PX-FOLLOWUP01")
        run = AnalysisRun.objects.create(
            patient=patient,
            requested_by=doctor,
            idempotency_key="followup-completed-analysis",
            status="completed",
        )
        client = auth_client(doctor)
        due_date = timezone.localdate() + timedelta(days=3)

        created = client.post(
            URL,
            {
                "patient_id": patient.pk,
                "analysis_run_id": run.pk,
                "task_type": "review_analysis",
                "due_date": due_date.isoformat(),
            },
            format="json",
        )

        assert created.status_code == 201
        body = created.json()
        assert body["patient_id"] == patient.pk
        assert body["patient_code"] == patient.patient_code
        assert body["analysis_run_id"] == run.pk
        assert body["status"] == "to_review"
        assert body["due_date"] == due_date.isoformat()

        listed = client.get(URL).json()
        assert listed["count"] == 1
        assert listed["results"][0]["id"] == body["id"]
        log = AuditLog.objects.get(action=audit.FOLLOWUP_LIST)
        assert log.patient == patient and log.meta == {"tasks": 1}

        updated = client.patch(
            f"{URL}{body['id']}/",
            {"status": "in_progress", "due_date": None},
            format="json",
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "in_progress"
        assert updated.json()["due_date"] is None
        update_log = AuditLog.objects.get(action=audit.FOLLOWUP_UPDATE)
        assert update_log.patient == patient
        assert set(update_log.meta["fields"]) == {"status", "due_date"}
        assert client.delete(f"{URL}{body['id']}/").status_code == 405

    def test_forbidden_patient_or_non_completed_analysis_cannot_be_linked(
        self, doctor, other_doctor, auth_client
    ):
        patient = Patient.objects.create(owner=doctor, patient_code="PX-FOLLOWUP02")
        foreign_patient = Patient.objects.create(owner=other_doctor, patient_code="PX-FOLLOWUP03")
        foreign_run = AnalysisRun.objects.create(
            patient=foreign_patient,
            idempotency_key="followup-foreign-analysis",
            status="completed",
        )
        pending_run = AnalysisRun.objects.create(
            patient=patient,
            idempotency_key="followup-pending-analysis",
            status="running",
        )
        client = auth_client(doctor)

        foreign_patient_response = client.post(
            URL,
            {"patient_id": foreign_patient.pk, "task_type": "patient_contact"},
            format="json",
        )
        assert foreign_patient_response.status_code == 404

        for run in (foreign_run, pending_run):
            response = client.post(
                URL,
                {"patient_id": patient.pk, "analysis_run_id": run.pk, "task_type": "review_analysis"},
                format="json",
            )
            assert response.status_code == 400
        assert FollowUpTask.objects.count() == 0

    def test_tasks_are_owner_scoped_and_clinician_only(self, doctor, other_doctor, make_user, auth_client, api_client):
        patient = Patient.objects.create(owner=other_doctor, patient_code="PX-FOLLOWUP04")
        task = FollowUpTask.objects.create(patient=patient, task_type="follow_up_visit")

        assert auth_client(doctor).get(URL).json()["count"] == 0
        assert auth_client(doctor).patch(f"{URL}{task.pk}/", {"status": "done"}, format="json").status_code == 404
        assert api_client.get(URL).status_code == 401
        assert auth_client(make_user("family")).get(URL).status_code == 403
