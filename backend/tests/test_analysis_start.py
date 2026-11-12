"""Day 5: POST /api/analysis/ (idempotency, ownership, human-in-the-loop) + runner safety nets. All data synthetic."""
from unittest import mock

import pytest

from apps.analysis import runner
from apps.analysis.models import AnalysisRun, RiskFinding, RiskSummary
from apps.audit.models import AuditLog
from apps.clinical.models import Medication
from apps.patients.models import Patient
from tests.factories import DrugFactory

URL = "/api/analysis/"


@pytest.fixture
def patient(doctor):
    return Patient.objects.create(owner=doctor, patient_code="PX-TEST0001", birth_year=1950)


@pytest.fixture
def meds(patient):
    d1, d2 = DrugFactory(), DrugFactory()
    return [
        Medication.objects.create(patient=patient, raw_text="testdrug a", drug=d1, resolution_status="resolved"),
        Medication.objects.create(patient=patient, raw_text="testdrug b", drug=d2, resolution_status="resolved"),
    ]


def body(patient, meds, key="key-12345678"):
    return {"patient_id": patient.id, "medication_ids": [m.id for m in meds], "idempotency_key": key}


@pytest.fixture
def enqueue():
    with mock.patch("apps.analysis.tasks.run_analysis.delay") as delay:
        yield delay


@pytest.mark.django_db
class TestStart:
    def test_roles(self, api_client, make_user, auth_client, patient, meds):
        assert api_client.post(URL, body(patient, meds), format="json").status_code == 401
        assert auth_client(make_user("family")).post(URL, body(patient, meds), format="json").status_code == 403

    def test_one_click_one_run(self, doctor, auth_client, patient, meds, enqueue, django_capture_on_commit_callbacks):
        client = auth_client(doctor)
        with django_capture_on_commit_callbacks(execute=True):
            first = client.post(URL, body(patient, meds), format="json")
        second = client.post(URL, body(patient, meds), format="json")
        assert (first.status_code, second.status_code) == (202, 200)
        assert first.json()["run_id"] == second.json()["run_id"] and second.json()["idempotent_replay"] is True
        assert AnalysisRun.objects.count() == 1
        enqueue.assert_called_once_with(first.json()["run_id"])
        snap = AnalysisRun.objects.get().input_snapshot
        assert snap["patient_context"]["age_band"] and "birth_year" not in snap["patient_context"]
        assert AuditLog.objects.filter(action="analysis_start").count() == 2

    def test_same_key_different_request_is_409(self, doctor, auth_client, patient, meds, enqueue):
        client = auth_client(doctor)
        client.post(URL, body(patient, meds), format="json")
        third = Medication.objects.create(patient=patient, raw_text="c", drug=DrugFactory(), resolution_status="resolved")
        r = client.post(URL, body(patient, meds + [third]), format="json")
        assert r.status_code == 409 and AnalysisRun.objects.count() == 1

    def test_other_doctor_cannot_reuse_key_or_patient(self, doctor, other_doctor, auth_client, patient, meds, enqueue):
        auth_client(doctor).post(URL, body(patient, meds), format="json")
        assert auth_client(other_doctor).post(URL, body(patient, meds), format="json").status_code == 404

    def test_unresolved_and_unconfirmed_scan_rejected(self, doctor, auth_client, patient, meds, enqueue):
        client = auth_client(doctor)
        loose = Medication.objects.create(patient=patient, raw_text="mystery")
        r = client.post(URL, body(patient, meds + [loose], "key-unresolved"), format="json")
        assert r.status_code == 400 and r.json()["error"]["details"]["code"] == "unresolved_medications"
        meds[0].source = "scan"
        meds[0].save(update_fields=["source"])
        r = client.post(URL, body(patient, meds, "key-unconfirmed"), format="json")
        assert r.status_code == 400 and r.json()["error"]["details"]["code"] == "unconfirmed_medications"
        assert AnalysisRun.objects.count() == 0

    def test_status_endpoint_hides_findings_until_completed_and_is_owner_only(
        self, doctor, other_doctor, auth_client, patient, meds, enqueue
    ):
        run_id = auth_client(doctor).post(URL, body(patient, meds), format="json").json()["run_id"]
        got = auth_client(doctor).get(f"{URL}{run_id}/").json()
        assert got["status"] == "queued" and got["findings_count"] is None and got["disclaimer_version"]
        assert auth_client(other_doctor).get(f"{URL}{run_id}/").status_code == 404


@pytest.mark.django_db
class TestRunner:
    def _run(self, doctor, auth_client, patient, meds):
        with mock.patch("apps.analysis.tasks.run_analysis.delay"):
            rid = auth_client(doctor).post(URL, body(patient, meds), format="json").json()["run_id"]
        return AnalysisRun.objects.get(pk=rid)

    def test_finding_without_evidence_is_downgraded_and_dosing_summary_replaced(
        self, doctor, auth_client, patient, meds
    ):
        run = self._run(doctor, auth_client, patient, meds)
        a, b = meds[0].drug_id, meds[1].drug_id
        result = {
            "findings": [
                {"drug_a_id": b, "drug_b_id": a, "severity": "major", "rationale": "x", "confidence": 0.9},
                {"drug_a_id": a, "drug_b_id": b, "severity": "moderate", "confidence": 0.7,
                 "evidence": [{"type": "interaction", "id": 1, "source": "testsource"}]},
            ],
            "summaries": {"doctor_en": "Take 500 mg less of it", "doctor_bn": "", "patient_card_bn": ""},
            "trace": [{"agent_name": "resolver", "step_order": 1, "input_summary": "call 01712345678"}],
        }
        with mock.patch.object(runner, "_invoke_pipeline", return_value=result):
            assert runner.execute_run(run.id) == "completed"
        severities = sorted(RiskFinding.objects.values_list("severity", flat=True))
        assert severities == ["moderate", "unknown"]
        assert "Take" not in RiskSummary.objects.get().doctor_summary_en
        assert "01712345678" not in run.traces.get().input_summary

    def test_malformed_finding_fails_run_and_duplicate_delivery_is_skipped(self, doctor, auth_client, patient, meds):
        run = self._run(doctor, auth_client, patient, meds)
        bad = {"findings": [{"drug_a_id": 999999, "drug_b_id": meds[0].drug_id, "severity": "unknown"}]}
        with mock.patch.object(runner, "_invoke_pipeline", return_value=bad):
            assert runner.execute_run(run.id) == "failed"
            assert runner.execute_run(run.id) == "skipped"
        run.refresh_from_db()
        assert run.status == "failed" and run.model_info["error"] == "malformed_finding"
        assert RiskFinding.objects.count() == 0