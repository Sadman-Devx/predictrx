from datetime import date

import pytest

from apps.clinical.models import Medication as ClinicalMedication
from apps.drugs.models import Drug
from apps.patients.models import Patient

URL = "/api/patients/"


def detail(pk):
    return f"{URL}{pk}/"


@pytest.mark.django_db
class TestAccessControl:
    def test_anonymous_gets_401(self, api_client):
        assert api_client.get(URL).status_code == 401
        assert api_client.post(URL, {}, format="json").status_code == 401

    @pytest.mark.parametrize("role", ["family", "admin"])
    def test_non_clinical_roles_get_403(self, make_user, auth_client, role):
        client = auth_client(make_user(role))
        assert client.get(URL).status_code == 403
        assert client.post(URL, {}, format="json").status_code == 403

    def test_pharmacist_can_create(self, make_user, auth_client):
        assert auth_client(make_user("pharmacist")).post(URL, {}, format="json").status_code == 201

    def test_doctor_cannot_read_or_change_another_doctors_patient(self, doctor, other_doctor, auth_client):
        theirs = auth_client(other_doctor).post(URL, {"birth_year": 1960}, format="json").json()
        mine = auth_client(doctor)
        assert mine.get(detail(theirs["id"])).status_code == 404  # 404, not 403: existence is not leaked
        assert mine.patch(detail(theirs["id"]), {"birth_year": 1999}, format="json").status_code == 404
        assert Patient.objects.get(pk=theirs["id"]).birth_year == 1960

    def test_list_only_contains_own_patients(self, doctor, other_doctor, auth_client):
        auth_client(doctor).post(URL, {}, format="json")
        auth_client(other_doctor).post(URL, {}, format="json")
        auth_client(other_doctor).post(URL, {}, format="json")
        body = auth_client(doctor).get(URL).json()
        assert body["count"] == 1
        assert Patient.objects.get(pk=body["results"][0]["id"]).owner == doctor

    def test_delete_and_put_are_not_allowed(self, doctor, auth_client):
        client = auth_client(doctor)
        pk = client.post(URL, {}, format="json").json()["id"]
        assert client.delete(detail(pk)).status_code == 405
        assert client.put(detail(pk), {}, format="json").status_code == 405


@pytest.mark.django_db
class TestCreateAndUpdate:
    def test_create_returns_server_generated_pseudonymous_code(self, doctor, auth_client):
        r = auth_client(doctor).post(URL, {"birth_year": 1958, "sex": "female", "weight_kg": "62.5"}, format="json")
        assert r.status_code == 201
        body = r.json()
        assert body["patient_code"].startswith("PX-") and len(body["patient_code"]) == 11
        assert (body["birth_year"], body["sex"], body["weight_kg"]) == (1958, "female", "62.5")
        assert "owner" not in body
        assert Patient.objects.get(pk=body["id"]).owner == doctor

    def test_client_cannot_choose_owner_or_code(self, doctor, other_doctor, auth_client):
        r = auth_client(doctor).post(URL, {"owner": other_doctor.id, "patient_code": "REAL-NAME-X"}, format="json")
        patient = Patient.objects.get(pk=r.json()["id"])
        assert patient.owner == doctor and patient.patient_code != "REAL-NAME-X"

    def test_codes_are_unique(self, doctor, auth_client):
        client = auth_client(doctor)
        codes = {client.post(URL, {}, format="json").json()["patient_code"] for _ in range(15)}
        assert len(codes) == 15

    def test_all_demographics_are_optional(self, doctor, auth_client):
        assert auth_client(doctor).post(URL, {}, format="json").status_code == 201

    @pytest.mark.parametrize("bad", [
        {"birth_year": 1850},
        {"birth_year": date.today().year + 1},
        {"weight_kg": "0"},
        {"weight_kg": "-5"},
        {"weight_kg": "501"},
        {"sex": "robot"},
    ])
    def test_invalid_values_are_rejected_with_error_shape(self, doctor, auth_client, bad):
        r = auth_client(doctor).post(URL, bad, format="json")
        assert r.status_code == 400
        assert "error" in r.json()
        assert Patient.objects.count() == 0

    def test_patch_updates_only_allowed_fields(self, doctor, auth_client):
        client = auth_client(doctor)
        created = client.post(URL, {"birth_year": 1950, "sex": "male"}, format="json").json()
        r = client.patch(detail(created["id"]), {"weight_kg": "70.0", "patient_code": "HACK", "id": 999}, format="json")
        assert r.status_code == 200
        patient = Patient.objects.get(pk=created["id"])
        assert str(patient.weight_kg) == "70.0"
        assert patient.patient_code == created["patient_code"] and patient.pk == created["id"]
        assert patient.birth_year == 1950  # untouched

    def test_patch_validates(self, doctor, auth_client):
        client = auth_client(doctor)
        pk = client.post(URL, {}, format="json").json()["id"]
        assert client.patch(detail(pk), {"birth_year": 1700}, format="json").status_code == 400

    def test_list_is_paginated_newest_first(self, doctor, auth_client):
        client = auth_client(doctor)
        ids = [client.post(URL, {}, format="json").json()["id"] for _ in range(3)]
        body = client.get(URL, {"page_size": 2}).json()
        assert body["count"] == 3 and len(body["results"]) == 2 and body["next"]
        assert body["results"][0]["id"] == ids[-1]


@pytest.mark.django_db
def test_openapi_schema_builds_with_patients(api_client):
    r = api_client.get("/api/schema/")
    assert r.status_code == 200
    assert b"/api/patients/" in r.content and b"/api/auth/register/" in r.content


@pytest.mark.django_db
def test_manual_medication_uses_clinical_record(doctor, auth_client):
    client = auth_client(doctor)
    patient = client.post(URL, {}, format="json").json()
    drug = Drug.objects.create(generic_name="paracetamol")

    response = client.post(
        f"{URL}{patient['id']}/medications/",
        {
            "raw_text": "Napa 500",
            "brand_name": "Napa",
            "strength": "500mg",
            "frequency": "daily",
            "drug_id": drug.id,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["generic_name"] == "paracetamol"
    medication = ClinicalMedication.objects.get(patient_id=patient["id"])
    assert medication.drug == drug
    assert medication.source == "manual"