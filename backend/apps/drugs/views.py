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