from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.audit import services as audit
from apps.patients.models import Patient
from core.permissions import IsDoctorOrPharmacist, IsPatientOwner

from .models import FollowUpTask
from .serializers import FollowUpTaskCreateSerializer, FollowUpTaskSerializer, FollowUpTaskUpdateSerializer


class FollowUpTaskViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Clinician-owned follow-up tasks. Tasks can be updated, but not silently deleted."""

    permission_classes = [IsDoctorOrPharmacist, IsPatientOwner]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return FollowUpTask.objects.none()
        queryset = FollowUpTask.objects.filter(patient__owner=self.request.user).select_related(
            "patient", "analysis_run"
        )
        status_filter = self.request.query_params.get("status")
        if status_filter in {value for value, _label in FollowUpTask.STATUSES}:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by(F("due_date").asc(nulls_last=True), "-created_at", "-pk")

    def get_serializer_class(self):
        if self.action == "create":
            return FollowUpTaskCreateSerializer
        if self.action in {"update", "partial_update"}:
            return FollowUpTaskUpdateSerializer
        return FollowUpTaskSerializer

    @transaction.atomic
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        rows = response.data.get("results", []) if isinstance(response.data, dict) else response.data
        patient_counts = {}
        for row in rows:
            patient_counts[row["patient_id"]] = patient_counts.get(row["patient_id"], 0) + 1
        for patient in Patient.objects.filter(owner=request.user, pk__in=patient_counts):
            audit.record(
                request,
                audit.FOLLOWUP_LIST,
                patient=patient,
                obj=patient,
                tasks=patient_counts[patient.pk],
            )
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(tags=["Follow-ups"], request=FollowUpTaskCreateSerializer, responses=FollowUpTaskSerializer)
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = FollowUpTask.objects.create(created_by=request.user, **serializer.validated_data)
        audit.record(
            request,
            audit.FOLLOWUP_CREATE,
            patient=task.patient,
            obj=task,
            task_type=task.task_type,
            linked_analysis=task.analysis_run_id is not None,
        )
        response = Response(FollowUpTaskSerializer(task).data, status=status.HTTP_201_CREATED)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(tags=["Follow-ups"], request=FollowUpTaskUpdateSerializer, responses=FollowUpTaskSerializer)
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        task = self.get_object()
        serializer = self.get_serializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changed_fields = [
            field for field, value in serializer.validated_data.items() if getattr(task, field) != value
        ]
        updated = serializer.save()
        audit.record(
            request,
            audit.FOLLOWUP_UPDATE,
            patient=task.patient,
            obj=task,
            fields=changed_fields,
        )
        response = Response(FollowUpTaskSerializer(updated).data)
        response["Cache-Control"] = "private, no-store"
        return response
