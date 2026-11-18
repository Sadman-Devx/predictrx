from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from core.permissions import IsAdminRole

from . import dashboard, services
from .models import EvalRun
from .serializers import EvalRunSerializer, EvalStartResponseSerializer, EvalStartSerializer


class EvalRunStartView(APIView):
    """POST /api/eval/run/ — start an evaluation of the `test` (default) or `dev` split. Admin only.

    202 = queued; the work happens in Celery (never inside the request). 409 `eval_in_progress` = one is already
    running. 400 `no_eval_cases` = the split is empty. The result is read from GET /api/eval/runs/{id}/.
    """

    permission_classes = [IsAdminRole]

    @extend_schema(tags=["Evaluation"], request=EvalStartSerializer, responses={202: EvalStartResponseSerializer})
    def post(self, request):
        ser = EvalStartSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            run = services.start_run(split=ser.validated_data["split"], user=request.user)
            audit.record(request, audit.EVAL_RUN, obj=run, split=run.split, n_cases=run.n_cases)
            transaction.on_commit(lambda: services.enqueue(run.id))
        body = {"run_id": run.id, "status": run.status, "split": run.split, "n_cases": run.n_cases}
        return Response(body, status=status.HTTP_202_ACCEPTED)


class EvalRunListView(generics.ListAPIView):
    """GET /api/eval/runs/ — metrics history, newest first. Filter: ?kind=pairs|brands &split=dev|test &status=..."""

    permission_classes = [IsAdminRole]
    serializer_class = EvalRunSerializer
    filterset_fields = ("kind", "split", "status")

    def get_queryset(self):
        return EvalRun.objects.order_by("-id")


class EvalRunDetailView(generics.RetrieveAPIView):
    """GET /api/eval/runs/{id}/ — poll while queued/running, read the metrics once `completed`."""

    permission_classes = [IsAdminRole]
    serializer_class = EvalRunSerializer
    queryset = EvalRun.objects.all()


class EvalDashboardView(APIView):
    """GET /api/eval/dashboard/ — everything the evaluation page shows, in one read-only call. Admin only.

    Only recorded runs and saved findings are read; nothing is computed here that a run did not measure. The test
    split carries counts only (no per-case list), the dev split also carries its pass/fail table. No patient data.
    """

    permission_classes = [IsAdminRole]

    @extend_schema(tags=["Evaluation"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(dashboard.build_dashboard())
