from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.audit import services as audit
from apps.clinical.models import Medication
from core.permissions import IsDoctorOrPharmacist, IsPatientOwner

from . import services
from .models import Patient
from .serializers import MedicationSerializer, PatientSerializer


class PatientViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    /api/patients/  (GET list, POST create)  ·  /api/patients/{id}/  (GET, PATCH)

    - Only doctors/pharmacists; each sees only the patients they own (a foreign id is a 404, not a 403,
      so existence is not leaked).
    - Every read/create/update writes an AuditLog row in the same transaction. If the audit write fails,
      the request fails: no patient data is returned without a trail.
    - No DELETE and no PUT by design (Patient is PROTECT-referenced by analysis runs).
    """

    serializer_class = PatientSerializer
    permission_classes = [IsDoctorOrPharmacist, IsPatientOwner]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # drf-spectacular schema generation has no real user
            return Patient.objects.none()
        return services.patients_for(self.request.user)

    @transaction.atomic
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        audit.record(request, audit.PATIENT_LIST, count=len(response.data["results"]))
        return response

    @transaction.atomic
    def retrieve(self, request, *args, **kwargs):
        patient = self.get_object()
        audit.record(request, audit.PATIENT_READ, patient=patient, obj=patient)
        return Response(self.get_serializer(patient).data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient = services.create_patient(owner=request.user, data=serializer.validated_data)
        audit.record(request, audit.PATIENT_CREATE, patient=patient, obj=patient)
        return Response(self.get_serializer(patient).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        patient = self.get_object()
        serializer = self.get_serializer(patient, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changed = services.update_patient(patient, serializer.validated_data)
        audit.record(request, audit.PATIENT_UPDATE, patient=patient, obj=patient, fields=changed)
        return Response(self.get_serializer(patient).data)



# Re-exported for backwards compatibility: the constants now live in apps/audit/services.py with every other action.
MEDICATION_LIST = audit.MEDICATION_LIST
MEDICATION_CREATE = audit.MEDICATION_CREATE


class MedicationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    /api/patients/{patient_pk}/medications/  (GET list, POST create)

    Nested under a patient. Only the patient's owner (doctor/pharmacist) can access; a foreign or missing patient
    is a plain 404 (existence is not leaked, and it is never a 500). Every read/write is audit-logged.
    Edit / confirm / delete of ONE medication lives in apps/clinical (PATCH/DELETE /api/medications/{id}/).
    """

    serializer_class = MedicationSerializer
    permission_classes = [IsDoctorOrPharmacist]
    http_method_names = ["get", "post", "head", "options"]

    def _get_patient(self) -> Patient:
        """Parent patient, fetched ONCE per request and only if the caller owns it (ownership comes from the token)."""
        if not hasattr(self, "_patient_cache"):
            patient = Patient.objects.filter(pk=self.kwargs["patient_pk"], owner=self.request.user).first()
            if patient is None:
                raise NotFound()
            self._patient_cache = patient
        return self._patient_cache

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Medication.objects.none()
        return services.list_medications(self._get_patient())

    @transaction.atomic
    def list(self, request, *args, **kwargs):
        patient = self._get_patient()
        response = super().list(request, *args, **kwargs)
        data = response.data
        count = len(data["results"]) if isinstance(data, dict) and "results" in data else len(data)
        audit.record(request, audit.MEDICATION_LIST, patient=patient, count=count)
        return response

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        patient = self._get_patient()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        medication = services.add_medication(patient, serializer.validated_data)
        audit.record(request, audit.MEDICATION_CREATE, patient=patient, obj=medication)
        return Response(self.get_serializer(medication).data, status=status.HTTP_201_CREATED)