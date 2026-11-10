from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets

from core.permissions import IsDoctorOrPharmacist

from . import services
from .filters import DrugFilter, InteractionFilter
from .serializers import DrugDetailSerializer, DrugSerializer, InteractionSerializer

_DATA_CAUTION = (
    "Reference data from public sources (openFDA, DDInter). Not validated for medical-care decisions. "
    "The absence of a record does NOT mean a combination is safe."
)


@extend_schema_view(
    list=extend_schema(tags=["Drugs"], summary="List drugs", description=_DATA_CAUTION),
    retrieve=extend_schema(tags=["Drugs"], summary="Drug detail with knowledge sources", description=_DATA_CAUTION),
)
class DrugViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsDoctorOrPharmacist]
    filterset_class = DrugFilter
    lookup_value_regex = r"\d+"  # keeps /api/drugs/search/ free for Day 4

    def get_queryset(self):
        return services.drug_detail_queryset() if self.action == "retrieve" else services.drugs_queryset()

    def get_serializer_class(self):
        return DrugDetailSerializer if self.action == "retrieve" else DrugSerializer


@extend_schema_view(
    list=extend_schema(tags=["Interactions"], summary="List interaction records", description=_DATA_CAUTION),
    retrieve=extend_schema(tags=["Interactions"], summary="Interaction record with source", description=_DATA_CAUTION),
)
class InteractionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsDoctorOrPharmacist]
    serializer_class = InteractionSerializer
    filterset_class = InteractionFilter
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return services.interactions_queryset()
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import CheckRequestSerializer, ResolveRequestSerializer


class DrugSearchView(APIView):
    """GET /api/drugs/search/?q=nap — autocomplete over generic names, aliases and brand names."""

    @extend_schema(parameters=[OpenApiParameter("q", str), OpenApiParameter("limit", int)], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        q = request.query_params.get("q", "")
        limit = min(int(request.query_params.get("limit", 10) or 10), 25)
        return Response({"results": services.search_names(q, limit)})


class ResolveMedicationsView(APIView):
    """POST /api/medications/resolve/ {"items": ["Napa 500", ...]} — never guesses; unresolved items come back with suggestions."""

    @extend_schema(request=ResolveRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        ser = ResolveRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response({"results": [services.resolve_name(item) for item in ser.validated_data["items"]]})


class CheckInteractionsView(APIView):
    """POST /api/interactions/check/ {"drugs": [...]} — every pair in the list, with evidence references."""

    @extend_schema(request=CheckRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        ser = CheckRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(services.check_interactions(ser.validated_data["drugs"]))
