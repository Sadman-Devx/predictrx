"""GET /api/analysis/runs/ — list of the signed-in clinician's own runs. All data synthetic."""
import pytest

from apps.analysis.models import AnalysisRun
from apps.patients.models import Patient

URL = "/api/analysis/runs/"


def _run(patient, user, key, status="completed", n_meds=3):
    return AnalysisRun.objects.create(
        patient=patient, requested_by=user, idempotency_key=key, status=status,
        input_snapshot={"medication_ids": list(range(1, n_meds + 1))},
    )


@pytest.fixture
def patient(doctor):
    return Patient.objects.create(owner=doctor, patient_code="PX-LIST0001")


@pytest.mark.django_db
class TestAnalysisList:
    def test_requires_login(self, api_client):
        assert api_client.get(URL).status_code == 401

    def test_family_role_is_forbidden(self, auth_client, make_user):
        assert auth_client(make_user("family")).get(URL).status_code == 403

    def test_lists_own_runs_newest_first(self, auth_client, doctor, patient):
        first = _run(patient, doctor, "key-00000001")
        second = _run(patient, doctor, "key-00000002", status="running", n_meds=2)
        r = auth_client(doctor).get(URL)
        assert r.status_code == 200
        rows = r.json()["results"]
        assert [x["run_id"] for x in rows] == [second.id, first.id]
        assert rows[0]["patient_code"] == "PX-LIST0001" and rows[0]["medication_count"] == 2
        assert rows[0]["findings_count"] == 0

    def test_does_not_leak_other_doctors_runs(self, auth_client, make_user, doctor, patient):
        other = make_user("doctor")
        other_patient = Patient.objects.create(owner=other, patient_code="PX-LIST0002")
        _run(other_patient, other, "key-00000009")
        _run(patient, doctor, "key-00000001")
        rows = auth_client(doctor).get(URL).json()["results"]
        assert len(rows) == 1 and rows[0]["patient_code"] == "PX-LIST0001"

    def test_status_filter(self, auth_client, doctor, patient):
        _run(patient, doctor, "key-00000001", status="completed")
        _run(patient, doctor, "key-00000002", status="failed")
        rows = auth_client(doctor).get(URL, {"status": "failed"}).json()["results"]
        assert len(rows) == 1 and rows[0]["status"] == "failed"

    def test_response_has_no_clinical_text(self, auth_client, doctor, patient):
        _run(patient, doctor, "key-00000001")
        row = auth_client(doctor).get(URL).json()["results"][0]
        assert set(row) == {"run_id", "patient_id", "patient_code", "status", "medication_count", "findings_count",
                            "started_at", "finished_at"}
