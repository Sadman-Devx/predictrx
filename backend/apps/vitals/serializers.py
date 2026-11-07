from rest_framework import serializers

from .models import VitalReading


class IngestSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=64)
    patient_id = serializers.CharField(max_length=64)
    spo2 = serializers.IntegerField(min_value=50, max_value=100)
    pulse = serializers.IntegerField(min_value=20, max_value=250)
    source = serializers.ChoiceField(choices=["esp32", "simulated", "manual"], default="esp32")


class VitalReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = VitalReading
        fields = ["id", "patient_id", "spo2", "pulse", "source",
                  "severity", "alert_reason", "recorded_at"]
