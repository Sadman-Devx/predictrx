from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth import DeviceTokenAuthentication
from .models import VitalReading
from .serializers import IngestSerializer, VitalReadingSerializer
from .tasks import analyze_reading, evaluate


class VitalsIngestView(APIView):
    """POST /api/vitals/ingest/  (called by ESP32)"""
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [AllowAny]  # auth enforced below via request.auth

    @extend_schema(
        tags=["Vitals (roadmap)"],
        summary="Ingest a device reading",
        request=IngestSerializer,
        responses={201: inline_serializer("VitalIngested", {"id": serializers.IntegerField()})},
    )
    def post(self, request):
        device = request.auth
        if device is None:
            return Response({"detail": "Device token required"}, status=status.HTTP_401_UNAUTHORIZED)

        ser = IngestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if data["device_id"] != device.device_id:
            return Response({"detail": "device_id mismatch"}, status=status.HTTP_403_FORBIDDEN)

        reading = VitalReading.objects.create(
            device=device,
            patient_id=data["patient_id"],
            spo2=data["spo2"],
            pulse=data["pulse"],
            source=data["source"],
        )
        try:
            analyze_reading.delay(reading.id)  # async via Celery + Redis
        except Exception:
            # Fallback if broker is down: evaluate inline
            reading.severity, reading.alert_reason = evaluate(reading.spo2, reading.pulse)
            reading.save(update_fields=["severity", "alert_reason"])

        return Response({"id": reading.id}, status=status.HTTP_201_CREATED)


class PatientVitalsView(APIView):
    """GET /api/vitals/patient/<patient_id>/?limit=50  (doctor dashboard)"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Vitals (roadmap)"],
        summary="Recent readings for a patient",
        parameters=[OpenApiParameter("limit", int, description="max 500, default 50")],
        responses=VitalReadingSerializer(many=True),
    )
    def get(self, request, patient_id):
        limit = min(int(request.query_params.get("limit", 50)), 500)
        qs = VitalReading.objects.filter(patient_id=patient_id)[:limit]
        return Response(VitalReadingSerializer(qs, many=True).data)
