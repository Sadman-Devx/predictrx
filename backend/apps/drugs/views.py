from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import (ResolveRequestSerializer, ResolveResponseSerializer, SearchQuerySerializer,
                          SearchResponseSerializer)


class ResolveMedicationsView(APIView):
    """POST /api/medications/resolve/ — brand/generic names -> generics. Synchronous, no LLM, no patient data.

    Unresolved items come back with a `reason` (and optional `candidates` to pick from). Nothing is guessed."""

    throttle_scope = "drug_lookup"

    @extend_schema(request=ResolveRequestSerializer, responses=ResolveResponseSerializer)
    def post(self, request):
        ser = ResolveRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        results = [services.resolve_brand(i["name"], i.get("strength") or None) for i in ser.validated_data["items"]]
        return Response({"results": results})


class DrugSearchView(APIView):
    """GET /api/drugs/search/?q=&limit= — autocomplete over brand + generic + alias names."""

    throttle_scope = "drug_lookup"

    @extend_schema(parameters=[SearchQuerySerializer], responses=SearchResponseSerializer)
    def get(self, request):
        ser = SearchQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        return Response({"results": services.search_drugs(ser.validated_data["q"], ser.validated_data["limit"])})
