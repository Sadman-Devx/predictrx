from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsDoctorOrPharmacist

from .models import Notification
from .serializers import NotificationListSerializer, NotificationSerializer


class NotificationListView(APIView):
    """GET /api/notifications/ — the latest ten events and unread count for the signed-in clinician."""

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Notifications"], responses=NotificationListSerializer)
    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user)
        body = {
            "unread_count": notifications.filter(read_at__isnull=True).count(),
            "results": list(
                notifications.select_related("scan__patient", "analysis_run__patient")
                .order_by("-created_at", "-id")[:10]
            ),
        }
        response = Response(NotificationListSerializer(body).data)
        response["Cache-Control"] = "private, no-store"
        return response


class NotificationReadView(APIView):
    """POST /api/notifications/{id}/read/ — mark one of the clinician's notifications as read."""

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Notifications"], request=None, responses=NotificationSerializer)
    def post(self, request, pk):
        notification = get_object_or_404(
            Notification.objects.filter(recipient=request.user).select_related("scan__patient", "analysis_run__patient"),
            pk=pk,
        )
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)
