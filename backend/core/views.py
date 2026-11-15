from django.http import JsonResponse
from django.views.defaults import page_not_found, server_error
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .exceptions import error_payload


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


# ---- JSON 404 / 500 for URLs under /api/ (wired as handler404 / handler500 in config/urls.py) ------------------------
# DRF only formats errors raised inside its own views. An unknown /api/... URL or a crash outside DRF would otherwise
# return Django's HTML page, which breaks the "one error shape" rule. Non-API paths keep Django's defaults.
def _is_api(request) -> bool:
    return request.path.startswith("/api/")


def api_not_found(request, exception=None):
    if _is_api(request):
        return JsonResponse(error_payload("not_found", "Not found."), status=404)
    return page_not_found(request, exception)


def api_server_error(request):
    if _is_api(request):
        return JsonResponse(
            error_payload("server_error", "Something went wrong on our side. Please try again."), status=500
        )
    return server_error(request)