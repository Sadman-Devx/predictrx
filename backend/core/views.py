from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(
    tags=["Health"],
    summary="Liveness check",
    responses=inline_serializer("Health", {"status": serializers.CharField(), "service": serializers.CharField()}),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness check. No DB access on purpose."""
    return Response({"status": "ok", "service": "predictrx-api"})