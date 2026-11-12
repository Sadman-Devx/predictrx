from itertools import combinations

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Interaction
from .serializers import InteractionCheckResponseSerializer, InteractionDetailSerializer


@extend_schema_view(get=extend_schema(tags=["Interactions"]))
class InteractionListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InteractionDetailSerializer
    queryset = Interaction.objects.select_related("drug_a", "drug_b").order_by(
        "drug_a__generic_name", "drug_b__generic_name", "source"
    )


class InteractionCheckView(APIView):
    """
    GET /api/interactions/check/?drug_ids=1,2,3

    Given a list of drug IDs, return all known interactions between them.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Interactions"],
        parameters=[
            OpenApiParameter(
                name="drug_ids",
                type=str,
                description="Comma-separated drug IDs. At least two IDs are needed to check pairs.",
            )
        ],
        responses=InteractionCheckResponseSerializer,
    )
    def get(self, request):
        raw = request.query_params.get("drug_ids", "")
        try:
            drug_ids = [int(x) for x in raw.split(",") if x.strip()]
        except ValueError:
            return Response(
                {"detail": "drug_ids must be comma-separated integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(drug_ids) < 2:
            return Response({"interactions": [], "checked_pairs": 0})

        # Build Q filter for all canonical pairs
        pair_q = Q()
        pairs = list(combinations(sorted(set(drug_ids)), 2))
        for a_id, b_id in pairs:
            pair_q |= Q(drug_a_id=a_id, drug_b_id=b_id)

        interactions = Interaction.objects.filter(pair_q).select_related("drug_a", "drug_b")
        serializer = InteractionDetailSerializer(interactions, many=True)
        return Response({"interactions": serializer.data, "checked_pairs": len(pairs)})


class InteractionDetailView(APIView):
    """
    GET /api/interactions/{id}/

    Return a single interaction detail.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Interactions"], responses=InteractionDetailSerializer)
    def get(self, request, pk):
        try:
            interaction = Interaction.objects.select_related("drug_a", "drug_b").get(pk=pk)
        except Interaction.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = InteractionDetailSerializer(interaction)
        return Response(serializer.data)
