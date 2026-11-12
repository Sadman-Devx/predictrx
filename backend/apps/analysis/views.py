from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsDoctorOrPharmacist

from . import services
from .models import AnalysisRun
from .serializers import AnalysisStartResponseSerializer, AnalysisStartSerializer, AnalysisStatusSerializer


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
    """GET /api/analysis/{id}/ — status for polling. No clinical content yet (Day 6 adds findings behind `completed`)."""

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Analysis"], responses=AnalysisStatusSerializer)
    def get(self, request, pk):
        run = AnalysisRun.objects.filter(pk=pk, patient__owner=request.user).first()
        if run is None:
            raise NotFound()  # foreign run == not found
        return Response(AnalysisStatusSerializer(run).data)