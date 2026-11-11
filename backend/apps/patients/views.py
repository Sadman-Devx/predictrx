from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.audit import services as audit
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



# Audit action constants for medication operations
MEDICATION_LIST = "medication_list"
MEDICATION_CREATE = "medication_create"


class MedicationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    /api/patients/{patient_pk}/medications/  (GET list, POST create)

    Nested under a patient. Only the patient's owner (doctor/pharmacist) can access.
    Every read/write is audit-logged.
    """

    serializer_class = MedicationSerializer
    permission_classes = [IsDoctorOrPharmacist]
    http_method_names = ["get", "post", "head", "options"]

    def _get_patient(self):
        """Fetch the parent patient, ensuring ownership."""
        patient = Patient.objects.get(pk=self.kwargs["patient_pk"])
        if patient.owner_id != self.request.user.id:
            from rest_framework.exceptions import NotFound

            raise NotFound()
        return patient

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            from apps.patients.models import Medication

            return Medication.objects.none()
        patient = self._get_patient()
        return services.list_medications(patient)

    @transaction.atomic
    def list(self, request, *args, **kwargs):
        patient = self._get_patient()
        response = super().list(request, *args, **kwargs)
        audit.record(request, MEDICATION_LIST, patient=patient, count=len(response.data.get("results", response.data)))
        return response

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        patient = self._get_patient()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        medication = services.add_medication(patient, serializer.validated_data)
        audit.record(request, MEDICATION_CREATE, patient=patient, obj=medication)
        return Response(self.get_serializer(medication).data, status=status.HTTP_201_CREATED)
