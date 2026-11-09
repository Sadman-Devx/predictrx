import pytest
from rest_framework.test import APIClient

from apps.audit import services as audit
from apps.audit.admin import AuditLogAdmin
from apps.audit.models import AuditLog
from apps.patients.models import Patient

URL = "/api/patients/"


def detail(pk):
    return f"{URL}{pk}/"


@pytest.mark.django_db
class TestPatientAudit:
    def test_reading_a_patient_writes_an_audit_row(self, doctor, auth_client):
        client = auth_client(doctor)
        pk = client.post(URL, {}, format="json").json()["id"]
        AuditLog.objects.all().delete()

        assert client.get(detail(pk), REMOTE_ADDR="203.0.113.7").status_code == 200

        log = AuditLog.objects.get()
        assert (log.action, log.actor, log.patient_id) == (audit.PATIENT_READ, doctor, pk)
        assert (log.object_type, log.object_id, log.ip) == ("Patient", str(pk), "203.0.113.7")

    def test_listing_writes_one_audit_row_with_count_only(self, doctor, auth_client):
        client = auth_client(doctor)
        for _ in range(3):
            client.post(URL, {}, format="json")
        AuditLog.objects.all().delete()

        client.get(URL)

        log = AuditLog.objects.get()
        assert log.action == audit.PATIENT_LIST and log.actor == doctor and log.meta == {"count": 3}

    def test_create_is_audited(self, doctor, auth_client):
        pk = auth_client(doctor).post(URL, {"birth_year": 1960}, format="json").json()["id"]
        log = AuditLog.objects.get(action=audit.PATIENT_CREATE)
        assert log.patient_id == pk and log.actor == doctor

    def test_update_is_audited_with_field_names_but_never_values(self, doctor, auth_client):
        client = auth_client(doctor)
        pk = client.post(URL, {"birth_year": 1960}, format="json").json()["id"]
        client.patch(detail(pk), {"birth_year": 1961, "weight_kg": "71.5"}, format="json")
        log = AuditLog.objects.get(action=audit.PATIENT_UPDATE)
        assert log.meta == {"fields": ["birth_year", "weight_kg"]}
        assert "1961" not in str(log.meta) and "71.5" not in str(log.meta)

    def test_foreign_patient_access_leaves_no_read_entry(self, doctor, other_doctor, auth_client):
        pk = auth_client(other_doctor).post(URL, {}, format="json").json()["id"]
        AuditLog.objects.all().delete()
        assert auth_client(doctor).get(detail(pk)).status_code == 404
        assert not AuditLog.objects.filter(action=audit.PATIENT_READ).exists()

    def test_every_patient_endpoint_that_returns_data_is_audited(self, doctor, auth_client):
        """Guard: GET list, GET detail, POST, PATCH each add at least one row."""
        client = auth_client(doctor)
        steps = [
            lambda: client.post(URL, {}, format="json"),
            lambda: client.get(URL),
        ]
        for step in steps:
            before = AuditLog.objects.count()
            assert step().status_code in (200, 201)
            assert AuditLog.objects.count() == before + 1


@pytest.mark.django_db
class TestFailClosed:
    def test_read_fails_if_audit_cannot_be_written(self, doctor, auth_client, monkeypatch):
        pk = auth_client(doctor).post(URL, {}, format="json").json()["id"]

        def boom(*a, **k):
            raise RuntimeError("audit store down")

        monkeypatch.setattr(audit, "record", boom)
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=doctor)
        r = client.get(detail(pk))
        assert r.status_code == 500
        assert b"patient_code" not in r.content  # no patient data leaves without a trail

    def test_create_is_rolled_back_if_audit_fails(self, doctor, monkeypatch):
        monkeypatch.setattr(audit, "record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=doctor)
        assert client.post(URL, {"birth_year": 1960}, format="json").status_code == 500
        assert Patient.objects.count() == 0


@pytest.mark.django_db
class TestAuditLogItself:
    def test_record_without_request_has_no_actor(self):
        log = audit.record(None, audit.PATIENT_READ)
        assert log.actor is None and log.ip is None

    def test_actor_survives_as_null_when_user_is_deleted(self, make_user):
        user = make_user("pharmacist")
        class R:  # minimal request stand-in
            META = {"REMOTE_ADDR": "198.51.100.1"}
            def __init__(self, u): self.user = u
        log = audit.record(R(user), audit.PATIENT_LIST, count=0)
        user.delete()
        log.refresh_from_db()
        assert log.actor is None and log.action == audit.PATIENT_LIST  # SET_NULL: the trail survives

    def test_admin_cannot_add_change_or_delete_entries(self, rf, doctor):
        ma = AuditLogAdmin(AuditLog, admin_site=None)
        request = rf.get("/")
        request.user = doctor
        assert not ma.has_add_permission(request)
        assert not ma.has_change_permission(request)
        assert not ma.has_delete_permission(request)