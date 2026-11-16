"""Day 10: what-if (Digital Twin). POST /api/twin/, GET /api/twin/{id}/, GET /api/analysis/{id}/twin/. All data synthetic."""
import uuid

import pytest

from apps.analysis.models import AnalysisRun, RiskFinding
from apps.audit.models import AuditLog
from apps.patients.models import Patient
from apps.twin.models import TwinScenario
from tests.factories import DrugFactory, make_interaction

URL = "/api/twin/"


@pytest.fixture
def patient(doctor):
    return Patient.objects.create(owner=doctor, patient_code="PX-TEST0010", birth_year=1950)


@pytest.fixture
def base_drugs():
    return [DrugFactory(), DrugFactory()]


def make_completed_run(patient, drugs, status="completed") -> AnalysisRun:
    snapshot = {
        "snapshot_version": 1,
        "medication_ids": [],
        "drug_ids": sorted(d.id for d in drugs),
        "medications": [
            {"medication_id": i, "raw_text": f"brand{i}", "brand_name": f"brand{i}", "strength": "",
             "frequency": "", "drug_id": d.id, "generic_name": d.generic_name,
             "resolution_status": "resolved", "source": "manual"}
            for i, d in enumerate(drugs, start=1)
        ],
    }
    return AnalysisRun.objects.create(patient=patient, requested_by=patient.owner,
                                      idempotency_key=f"key-{uuid.uuid4().hex[:12]}", status=status,
                                      input_snapshot=snapshot)


@pytest.fixture
def run(patient, base_drugs):
    r = make_completed_run(patient, base_drugs)
    ix = make_interaction(base_drugs[0], base_drugs[1], severity="minor")
    RiskFinding.objects.create(run=r, drug_a=base_drugs[0], drug_b=base_drugs[1], severity="minor",
                               rationale="synthetic", confidence="0.80", verification_status="verified",
                               evidence=[{"type": "interaction", "id": ix.id, "source": "testsource"}])
    return r


def post(client, run, drug, **extra):
    return client.post(URL, {"base_run_id": run.id, "drug_id": drug.id, **extra}, format="json")


def test_added_finding_has_evidence_and_comparison(auth_client, doctor, run, base_drugs):
    new = DrugFactory()
    make_interaction(new, base_drugs[0], severity="major")  # the second base drug has no record

    resp = post(auth_client(doctor), run, new)

    assert resp.status_code == 201
    body = resp.json()
    assert body["simulation"] is True
    assert body["hypothetical_drug"]["id"] == new.id
    assert len(body["added_findings"]) == 1
    finding = body["added_findings"][0]
    assert finding["severity"] == "major"
    assert finding["evidence"] and finding["evidence"][0]["type"] == "interaction"
    assert finding["verification_status"] == "verified"
    assert len(body["no_record_pairs"]) == 1
    assert body["comparison"]["before"]["highest_severity"] == "minor"
    assert body["comparison"]["after"]["highest_severity"] == "major"
    assert body["comparison"]["highest_severity_changed"] is True
    assert resp["Cache-Control"] == "no-store"


def test_no_record_is_never_safe(auth_client, doctor, run):
    resp = post(auth_client(doctor), run, DrugFactory())

    assert resp.status_code == 201
    body = resp.json()
    assert body["added_findings"] == []
    assert len(body["no_record_pairs"]) == 2
    assert all("does not mean" in pair["note"] for pair in body["no_record_pairs"])
    assert body["comparison"]["highest_severity_changed"] is False


def test_same_request_returns_the_same_scenario(auth_client, doctor, run, base_drugs):
    new = DrugFactory()
    make_interaction(new, base_drugs[0], severity="moderate")
    client = auth_client(doctor)

    first, second = post(client, run, new), post(client, run, new)

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["scenario_id"] == second.json()["scenario_id"]
    assert TwinScenario.objects.count() == 1


def test_conflicting_sources_are_shown_as_conflict(auth_client, doctor, run, base_drugs):
    new = DrugFactory()
    make_interaction(new, base_drugs[0], severity="major", source="source_a")
    make_interaction(new, base_drugs[0], severity="minor", source="source_b")

    finding = post(auth_client(doctor), run, new).json()["added_findings"][0]

    assert finding["verification_status"] == "conflict"
    assert finding["severity_conflict"] is True
    assert len(finding["evidence"]) == 2


def test_dosing_text_from_the_table_is_never_shown(auth_client, doctor, run, base_drugs):
    new = DrugFactory()
    make_interaction(new, base_drugs[0], severity="moderate",
                     mechanism="Take 500 mg twice daily.", management="Increase the dose slowly.")

    finding = post(auth_client(doctor), run, new).json()["added_findings"][0]

    assert "500" not in finding["rationale"]
    assert finding["management"] is None


def test_foreign_run_is_404(auth_client, other_doctor, run):
    resp = post(auth_client(other_doctor), run, DrugFactory())

    assert resp.status_code == 404
    assert TwinScenario.objects.count() == 0


def test_base_run_must_be_completed(auth_client, doctor, patient, base_drugs):
    queued = make_completed_run(patient, base_drugs, status="queued")

    resp = post(auth_client(doctor), queued, DrugFactory())

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "base_run_not_completed"


def test_drug_already_in_run_is_rejected(auth_client, doctor, run, base_drugs):
    resp = post(auth_client(doctor), run, base_drugs[0])

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "drug_already_in_run"


def test_unknown_drug_is_rejected(auth_client, doctor, run):
    resp = auth_client(doctor).post(URL, {"base_run_id": run.id, "generic_name": "no-such-drug"}, format="json")

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "drug_not_found"


def test_exactly_one_of_drug_id_or_generic_name(auth_client, doctor, run):
    both = auth_client(doctor).post(URL, {"base_run_id": run.id, "drug_id": 1, "generic_name": "x"}, format="json")
    neither = auth_client(doctor).post(URL, {"base_run_id": run.id}, format="json")

    assert both.status_code == neither.status_code == 400
    assert both.json()["error"]["code"] == neither.json()["error"]["code"] == "validation_error"


def test_generic_name_works_like_drug_id(auth_client, doctor, run):
    new = DrugFactory()

    resp = auth_client(doctor).post(URL, {"base_run_id": run.id, "generic_name": new.generic_name.upper()},
                                    format="json")

    assert resp.status_code == 201
    assert resp.json()["hypothetical_drug"]["id"] == new.id


def test_family_user_cannot_use_twin(auth_client, make_user, run):
    resp = post(auth_client(make_user("family")), run, DrugFactory())

    assert resp.status_code == 403


def test_run_and_read_are_audited(auth_client, doctor, run):
    client = auth_client(doctor)
    scenario_id = post(client, run, DrugFactory()).json()["scenario_id"]

    assert client.get(f"{URL}{scenario_id}/").status_code == 200
    assert client.get(f"/api/analysis/{run.id}/twin/").status_code == 200

    actions = list(AuditLog.objects.filter(patient=run.patient).values_list("action", flat=True))
    assert actions.count("twin_run") == 1
    assert actions.count("twin_read") == 2


def test_detail_and_history_are_owner_only(auth_client, doctor, other_doctor, run):
    scenario_id = post(auth_client(doctor), run, DrugFactory()).json()["scenario_id"]
    other = auth_client(other_doctor)

    assert other.get(f"{URL}{scenario_id}/").status_code == 404
    assert other.get(f"/api/analysis/{run.id}/twin/").status_code == 404


def test_history_lists_newest_first(auth_client, doctor, run):
    client = auth_client(doctor)
    first = post(client, run, DrugFactory()).json()["scenario_id"]
    second = post(client, run, DrugFactory()).json()["scenario_id"]

    rows = client.get(f"/api/analysis/{run.id}/twin/").json()["results"]

    assert [r["scenario_id"] for r in rows] == [second, first]
