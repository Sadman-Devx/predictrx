from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import (
    DrugSearchResponseSerializer,
    ResolveRequestSerializer,
    ResolveResponseSerializer,
)
from .services import resolve_many, search_drugs


class ResolveMedicationsView(APIView):
    """POST /api/medications/resolve/: brand/typed names -> generic (never guesses)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "resolve"

    @extend_schema(request=ResolveRequestSerializer, responses=ResolveResponseSerializer)
    def post(self, request):
        serializer = ResolveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = resolve_many(serializer.validated_data["items"])
        return Response({"results": results})


class DrugSearchView(APIView):
    """GET /api/drugs/search/?q=nap&limit=10: autocomplete over brand + generic names."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "drug_search"

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, required=True),
            OpenApiParameter("limit", int, required=False),
        ],
        responses=DrugSearchResponseSerializer,
    )
    def get(self, request):
        q = request.query_params.get("q", "")
        try:
            limit = max(1, min(int(request.query_params.get("limit", 10)), 20))
        except ValueError:
            limit = 10
        return Response({"results": search_drugs(q, limit)})