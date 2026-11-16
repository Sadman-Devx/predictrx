"""Family (NRB) endpoints: a read-only, consent-gated view for linked family users.

  GET /api/family/patients/                  patients the caller is linked to (consent active)
  GET /api/family/patients/{id}/summary/     the read-only plain-language summary of one of them

Only the `family` role passes the permission class; access to a SPECIFIC patient is then re-checked on every request
(active link + active `family_view` consent, apps/patients/family.py). Every patient that is shown writes an AuditLog
`family_view` row in the same transaction: if the audit write fails, nothing is returned. Responses are `no-store`.
"""
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from core.permissions import IsFamilyRole

from . import family
from .serializers import FamilyPatientItemSerializer, FamilyPatientListSerializer, FamilySummarySerializer
from .views import envelope


def _no_store(response: Response) -> Response:
    """Health-related content must not sit in a shared or browser cache."""
    response["Cache-Control"] = "no-store"
    return response


class FamilyPatientListView(APIView):
    permission_classes = [IsFamilyRole]

    @extend_schema(tags=["Family"], responses=FamilyPatientListSerializer)
    def get(self, request):
        with transaction.atomic():
            links, items = family.list_for_family(request.user)
            for link in links:
                audit.record(request, audit.FAMILY_VIEW, patient=link.patient, obj=link, surface="list")
        return _no_store(Response(envelope(FamilyPatientItemSerializer(items, many=True).data)))


class FamilyPatientSummaryView(APIView):
    permission_classes = [IsFamilyRole]

    @extend_schema(tags=["Family"], responses=FamilySummarySerializer)
    def get(self, request, pk):
        with transaction.atomic():
            link = family.get_usable_link(request.user, pk)
            body = family.summary_for_family(link)
            audit.record(request, audit.FAMILY_VIEW, patient=link.patient, obj=link, surface="summary")
        return _no_store(Response(FamilySummarySerializer(body).data))