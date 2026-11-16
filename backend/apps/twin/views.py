from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from core.permissions import IsDoctorOrPharmacist

from . import services
from .serializers import TwinListSerializer, TwinScenarioSerializer, TwinStartSerializer


def _no_store(response: Response) -> Response:
    """A scenario is patient-related clinical content: it must not sit in a browser or proxy cache."""
    response["Cache-Control"] = "no-store"
    return response


class TwinStartView(APIView):
    """POST /api/twin/ — what-if: add one hypothetical drug to a completed analysis and compare the picture.

    Body: `{base_run_id, drug_id}` or `{base_run_id, generic_name}`. Computed from the interaction table only (no LLM),
    so it answers in the same request. It is a SIMULATION FOR EXPLORATION: the response says so and lists its limits.

    201 = new scenario stored · 200 = the same request was already answered, the existing scenario is returned.
    400 `drug_not_found` / `drug_already_in_run` / `validation_error` · 404 = run is not yours (or missing) ·
    409 `base_run_not_completed`. Every call is written to the AuditLog (`twin_run`).
    """

    permission_classes = [IsDoctorOrPharmacist]
    throttle_scope = "twin"

    @extend_schema(tags=["Twin"], request=TwinStartSerializer,
                   responses={201: TwinScenarioSerializer, 200: TwinScenarioSerializer})
    def post(self, request):
        ser = TwinStartSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            scenario, created = services.run_scenario(request.user, **ser.validated_data)
            payload = services.scenario_payload(scenario)
            audit.record(request, audit.TWIN_RUN, patient=scenario.patient, obj=scenario, replay=not created,
                         base_run_id=scenario.base_run_id, new_findings=len(payload["added_findings"]),
                         no_record_pairs=len(payload["no_record_pairs"]))
        body = TwinScenarioSerializer(payload).data
        return _no_store(Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK))


class TwinDetailView(APIView):
    """GET /api/twin/{id}/ — read one stored scenario (owner only). Reading it is audited (`twin_read`).

    The numbers are a snapshot as of `created_at`: a scenario is never recomputed in place.
    """

    permission_classes = [IsDoctorOrPharmacist]
    throttle_scope = "twin_read"

    @extend_schema(tags=["Twin"], responses=TwinScenarioSerializer)
    def get(self, request, pk):
        scenario = services.get_owned_scenario(request.user, pk)
        payload = services.scenario_payload(scenario)
        audit.record(request, audit.TWIN_READ, patient=scenario.patient, obj=scenario, op="detail",
                     base_run_id=scenario.base_run_id)
        return _no_store(Response(TwinScenarioSerializer(payload).data))


class TwinListView(APIView):
    """GET /api/analysis/{id}/twin/ — the what-if history of one analysis, newest first (owner only).

    Compact rows only (drug, when, how many findings it added, highest severity after). Open one scenario with
    GET /api/twin/{id}/. Listing is audited (`twin_read`, op=list).
    """

    permission_classes = [IsDoctorOrPharmacist]
    throttle_scope = "twin_read"

    @extend_schema(tags=["Twin"], responses=TwinListSerializer)
    def get(self, request, pk):
        run, scenarios = services.list_scenarios(request.user, pk)
        audit.record(request, audit.TWIN_READ, patient=run.patient, obj=run, op="list", count=len(scenarios))
        body = {"base_run_id": run.id, "results": [services.scenario_summary(s) for s in scenarios]}
        return _no_store(Response(TwinListSerializer(body).data))

