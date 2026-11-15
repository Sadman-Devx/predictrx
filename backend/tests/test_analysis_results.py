"""Day 6: GET /api/analysis/{id}/ (progress + result), GET /api/analysis/{id}/trace/, live progress. All data synthetic."""
import uuid

import pytest

from apps.analysis import runner
from apps.analysis.models import AnalysisRun
from apps.audit.models import AuditLog
from apps.clinical.models import Medication
from apps.patients.models import Patient
from tests.factories import DrugFactory, make_interaction

URL = "/api/analysis/"


@pytest.fixture
def patient(doctor):
    return Patient.objects.create(owner=doctor, patient_code="PX-TEST0006", birth_year=1950)


@pytest.fixture
def meds(patient):
    return [
        Medication.objects.create(patient=patient, raw_text=f"testbrand {n}", brand_name=f"testbrand{n}",
                                  drug=DrugFactory(), resolution_status="resolved")
        for n in range(3)
    ]


def make_run(patient, meds, status="queued", **model_info) -> AnalysisRun:
    snapshot = {
        "snapshot_version": 1,
        "medication_ids": [m.id for m in meds],
        "drug_ids": sorted(m.drug_id for m in meds),
        "medications": [
            {"medication_id": m.id, "raw_text": m.raw_text, "brand_name": m.brand_name, "strength": "",
             "frequency": "", "drug_id": m.drug_id, "generic_name": m.drug.generic_name,
             "resolution_status": "resolved", "source": "manual"}
            for m in meds
        ],
    }
    return AnalysisRun.objects.create(patient=patient, requested_by=patient.owner,
                                      idempotency_key=f"key-{uuid.uuid4().hex[:12]}", status=status,
                                      input_snapshot=snapshot, model_info=model_info)


def complete(run, meds):
    d1, d2, d3 = (m.drug for m in meds)
    ix_moderate = make_interaction(d1, d2, severity="moderate")
    ix_major = make_interaction(d1, d3, severity="major")
    result = {
        "findings": [
            {"drug_a_id": d1.id, "drug_b_id": d2.id, "severity": "moderate", "rationale": "synthetic moderate",
             "confidence": 0.7, "verification_status": "verified",
             "evidence": [{"type": "interaction", "id": ix_moderate.id, "source": "testsource"}]},
            {"drug_a_id": d2.id, "drug_b_id": d3.id, "severity": "unknown", "rationale": "no record",
             "confidence": 0, "verification_status": "unverified", "evidence": []},
            {"drug_a_id": d3.id, "drug_b_id": d1.id, "severity": "major", "rationale": "synthetic major",
             "confidence": 0.9, "verification_status": "conflict",
             "evidence": [{"type": "interaction", "id": ix_major.id, "source": "testsource"},
                          {"type": "chunk", "id": 999999, "source": "openfda_label"}]},
        ],
        "summaries": {"doctor_en": "Interaction review: three drugs.", "doctor_bn": "", "patient_card_bn": ""},
        "trace": [
            {"agent_name": "verifier", "step_order": 5, "output_summary": "done", "latency_ms": 7},
            {"agent_name": "resolver", "step_order": 1, "output_summary": "done", "latency_ms": 5},
        ],
    }
    runner.persist_result(run, result)
    run.refresh_from_db()
    return ix_major


@pytest.mark.django_db
class TestDetail:
    def test_running_run_shows_progress_and_no_clinical_content(self, doctor, auth_client, patient, meds):
        run = make_run(patient, meds, "running", progress={"completed_agents": ["resolver", "clinical_notes"]})
        got = auth_client(doctor).get(f"{URL}{run.id}/").json()
        assert got["status"] == "running" and got["is_final"] is False and got["current_step"] == "drug_interaction"
        assert [s["status"] for s in got["progress"]] == ["done", "done", "running", "pending", "pending"]
        for key in ("findings", "findings_count", "summary", "medications", "gaps", "guardrail_violations"):
            assert got[key] is None
        assert got["disclaimer"]["text_en"] and got["disclaimer"]["text_bn"]
        assert not AuditLog.objects.filter(action="analysis_read").exists()  # polls carry no clinical content

    def test_failed_run_marks_the_step_it_stopped_at(self, doctor, auth_client, patient, meds):
        run = make_run(patient, meds, "failed", error="pipeline_error", progress={"completed_agents": ["resolver"]})
        got = auth_client(doctor).get(f"{URL}{run.id}/").json()
        assert got["error_code"] == "pipeline_error" and got["is_final"] is True and got["findings"] is None
        assert [s["status"] for s in got["progress"]] == ["done", "failed", "pending", "pending", "pending"]

    def test_enqueue_failure_marks_no_step_as_failed(self, doctor, auth_client, patient, meds):
        run = make_run(patient, meds, "failed", error="enqueue_failed")
        got = auth_client(doctor).get(f"{URL}{run.id}/").json()
        assert {s["status"] for s in got["progress"]} == {"pending"} and got["current_step"] is None

    def test_completed_result_is_sorted_cited_and_audited(self, doctor, auth_client, patient, meds):
        run = make_run(patient, meds, "running")
        ix_major = complete(run, meds)
        got = auth_client(doctor).get(f"{URL}{run.id}/").json()

        assert got["status"] == "completed" and got["is_final"] is True and got["findings_count"] == 3
        assert [f["severity"] for f in got["findings"]] == ["major", "moderate", "unknown"]
        assert {s["status"] for s in got["progress"]} == {"done"}
        assert got["summary"]["doctor_summary_en"] and "patient_card_bn" not in got["summary"]
        assert len(got["medications"]) == 3

        major = got["findings"][0]
        assert major["verification_status"] == "conflict" and major["confidence"] == 0.9
        assert major["confidence_basis"]["evidence_count"] == 2
        assert major["entered_names_a"] and major["drug_a"]["generic_name"]
        found = {e["type"]: e for e in major["evidence"]}
        assert found["interaction"]["available"] is True and found["interaction"]["id"] == ix_major.id
        assert found["interaction"]["license_note"] == "synthetic test data"
        assert found["chunk"]["available"] is False  # record no longer exists: shown honestly, not dropped

        unknown = got["findings"][2]
        assert unknown["evidence"] == [] and unknown["confidence_basis"]["sources"] == []
        assert AuditLog.objects.filter(action="analysis_read", patient=patient).count() == 1

    def test_completed_detail_has_constant_query_count(self, doctor, auth_client, patient, meds, django_assert_max_num_queries):
        run = make_run(patient, meds, "running")
        complete(run, meds)
        with django_assert_max_num_queries(12):  # auth + run + findings + 2 evidence lookups + summary + audit
            assert auth_client(doctor).get(f"{URL}{run.id}/").status_code == 200

    def test_roles_and_ownership(self, api_client, make_user, auth_client, other_doctor, patient, meds):
        run = make_run(patient, meds)
        assert api_client.get(f"{URL}{run.id}/").status_code == 401
        assert auth_client(make_user("family")).get(f"{URL}{run.id}/").status_code == 403
        assert auth_client(other_doctor).get(f"{URL}{run.id}/").status_code == 404
        assert auth_client(other_doctor).get(f"{URL}{run.id}/trace/").status_code == 404


@pytest.mark.django_db
class TestTrace:
    def test_trace_is_ordered_audited_and_complete(self, doctor, auth_client, patient, meds):
        run = make_run(patient, meds, "running")
        complete(run, meds)
        got = auth_client(doctor).get(f"{URL}{run.id}/trace/").json()
        assert got["available"] is True and got["status"] == "completed"
        assert [t["agent_name"] for t in got["traces"]] == ["resolver", "verifier"]
        assert got["total_latency_ms"] == 12
        assert AuditLog.objects.filter(action="analysis_trace_read", patient=patient).count() == 1

    def test_trace_before_completion_returns_steps_only(self, doctor, auth_client, patient, meds):
        run = make_run(patient, meds, "running", progress={"completed_agents": ["resolver"]})
        got = auth_client(doctor).get(f"{URL}{run.id}/trace/").json()
        assert got["available"] is False and got["traces"] == [] and got["total_latency_ms"] is None
        assert [s["status"] for s in got["steps"]][:2] == ["done", "running"]
        assert not AuditLog.objects.filter(action="analysis_trace_read").exists()


@pytest.mark.django_db
class TestLiveProgress:
    def test_record_progress_updates_running_run_only_when_it_changes(self, patient, meds):
        run = make_run(patient, meds, "running")
        runner._record_progress(run, {"trace": [{"agent_name": "resolver"}, {"agent_name": "clinical_notes"}]})
        run.refresh_from_db()
        assert run.model_info["progress"]["completed_agents"] == ["resolver", "clinical_notes"]

        AnalysisRun.objects.filter(pk=run.pk).update(status="completed")
        runner._record_progress(run, {"trace": [{"agent_name": "resolver"}]})
        run.refresh_from_db()
        assert run.model_info["progress"]["completed_agents"] == ["resolver", "clinical_notes"]  # finished run untouched