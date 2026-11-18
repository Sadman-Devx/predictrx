from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analysis.models import AnalysisRun
from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.clinical.models import Medication
from apps.followups.models import FollowUpTask
from apps.patients.models import Patient
from apps.patients.services import patients_for
from core.permissions import IsDoctorOrPharmacist


class DashboardPatientSerializer(serializers.ModelSerializer):
    medication_count = serializers.IntegerField(source="medication_total", read_only=True)

    class Meta:
        model = Patient
        fields = ["id", "patient_code", "medication_count"]
        read_only_fields = fields


class DashboardActivitySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    event = serializers.ChoiceField(
        choices=[
            "analysis_run",
            "patient_opened",
            "family_viewed",
            "consent_granted",
            "consent_revoked",
            "consent_changed",
        ]
    )
    patient_code = serializers.CharField()
    at = serializers.DateTimeField()


class DashboardSummarySerializer(serializers.Serializer):
    total_patients = serializers.IntegerField()
    total_analyses = serializers.IntegerField()
    pending_reviews = serializers.IntegerField()
    pending_followups = serializers.IntegerField()
    overdue_followups = serializers.IntegerField()
    recent_patients = DashboardPatientSerializer(many=True)
    recent_activity = DashboardActivitySerializer(many=True)


def _activity_type(entry: AuditLog) -> str | None:
    if entry.action == audit.ANALYSIS_START:
        return "analysis_run"
    if entry.action == audit.PATIENT_READ:
        return "patient_opened"
    if entry.action == audit.FAMILY_VIEW:
        return "family_viewed"
    if entry.action == audit.CONSENT_CHANGE:
        change = entry.meta.get("change") if isinstance(entry.meta, dict) else None
        return f"consent_{change}" if change in {"granted", "revoked"} else "consent_changed"
    return None


class DashboardSummaryView(APIView):
    """GET /api/dashboard/summary/ — owner-scoped dashboard counts and recent activity."""

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Dashboard"], responses=DashboardSummarySerializer)
    @transaction.atomic
    def get(self, request):
        recent_patients = list(patients_for(request.user)[:3])
        total_patients = Patient.objects.filter(owner=request.user).count()
        total_analyses = AnalysisRun.objects.filter(patient__owner=request.user).count()
        pending_reviews = (
            Medication.objects.filter(
                patient__owner=request.user,
                scan__status="extracted",
                source="scan",
                confirmed_by_user=False,
            )
            .values("scan_id")
            .distinct()
            .count()
        )
        followups = FollowUpTask.objects.filter(
            patient__owner=request.user, status__in=["to_review", "in_progress"]
        )
        pending_followups = followups.count()
        overdue_followups = followups.filter(due_date__lt=timezone.localdate()).count()

        activity_rows = (
            AuditLog.objects.filter(
                patient__owner=request.user,
                action__in=[
                    audit.ANALYSIS_START,
                    audit.PATIENT_READ,
                    audit.FAMILY_VIEW,
                    audit.CONSENT_CHANGE,
                ],
            )
            .select_related("patient")
            .order_by("-at", "-id")[:5]
        )
        recent_activity = [
            {
                "id": entry.id,
                "event": event,
                "patient_code": entry.patient.patient_code,
                "at": entry.at,
            }
            for entry in activity_rows
            if (event := _activity_type(entry)) is not None
        ]

        audit.record(request, audit.PATIENT_LIST, count=len(recent_patients), view="dashboard")
        payload = {
            "total_patients": total_patients,
            "total_analyses": total_analyses,
            "pending_reviews": pending_reviews,
            "pending_followups": pending_followups,
            "overdue_followups": overdue_followups,
            "recent_patients": recent_patients,
            "recent_activity": recent_activity,
        }
        response = Response(DashboardSummarySerializer(payload).data)
        response["Cache-Control"] = "private, no-store"
        return response
