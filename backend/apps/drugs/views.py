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