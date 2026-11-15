from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from core.permissions import IsDoctorOrPharmacist

from . import results, services
from .models import AnalysisRun
from .serializers import (AnalysisDetailSerializer, AnalysisStartResponseSerializer, AnalysisStartSerializer,
                          AnalysisTraceSerializer)


def get_owned_run(request, pk: int) -> AnalysisRun:
    """Ownership is derived from the authenticated user. A foreign (or missing) run is a plain 404."""
    run = AnalysisRun.objects.select_related("patient").filter(pk=pk, patient__owner=request.user).first()
    if run is None:
        raise NotFound()
    return run


class AnalysisStartView(APIView):
    """POST /api/analysis/ — start a run. Returns immediately with a run id; the work happens in Celery.

    202 = new run created and queued · 200 = same idempotency key re-sent, the existing run is returned.
    """

    permission_classes = [IsDoctorOrPharmacist]
    throttle_scope = "analysis"

    @extend_schema(
        tags=["Analysis"],
        request=AnalysisStartSerializer,
        responses={202: AnalysisStartResponseSerializer, 200: AnalysisStartResponseSerializer},
    )
    def post(self, request):
        ser = AnalysisStartSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            run, created = services.start_analysis(request, **ser.validated_data)
        body = {
            "run_id": run.id,
            "status": run.status,
            "idempotent_replay": not created,
            "disclaimer_version": settings.DISCLAIMER_VERSION,
        }
        return Response(body, status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK)


class AnalysisDetailView(APIView):
    """GET /api/analysis/{id}/ — poll while running, read the result once `status == completed`.

    * queued / running / failed: status + pipeline progress only. Clinical fields are `null` (never a partial result).
    * completed: findings (major -> unknown), doctor summary, frozen medication list, gaps, guardrail flags.
      This read returns patient-related clinical content, so it is written to the AuditLog.
    * Status polls carry no clinical content and are NOT audited (a 2-second poll would flood the log).
    """

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Analysis"], responses=AnalysisDetailSerializer)
    def get(self, request, pk):
        run = get_owned_run(request, pk)
        if run.status != "completed":
            return Response(AnalysisDetailSerializer(run).data)

        context = results.result_context(run)
        audit.record(request, audit.ANALYSIS_READ, patient=run.patient, obj=run, findings=len(context["findings"]))
        return Response(AnalysisDetailSerializer(run, context=context).data)


class AnalysisTraceView(APIView):
    """GET /api/analysis/{id}/trace/ — agent trace for the UI (which agent ran, tools called, latency).

    Before the run completes only the step list (`steps`, names + status) is returned; `traces` is empty and
    `available` is false. Trace rows are redacted summaries; reading them is audited.
    """

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Analysis"], responses=AnalysisTraceSerializer)
    def get(self, request, pk):
        run = get_owned_run(request, pk)
        traces = list(run.traces.order_by("step_order", "id")) if run.status == "completed" else []
        if traces:
            audit.record(request, audit.ANALYSIS_TRACE_READ, patient=run.patient, obj=run, steps=len(traces))
        return Response(AnalysisTraceSerializer(run, context={"traces": traces}).data)