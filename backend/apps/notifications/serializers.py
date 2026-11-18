from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    scan_id = serializers.IntegerField(read_only=True, allow_null=True)
    analysis_run_id = serializers.IntegerField(read_only=True, allow_null=True)
    patient_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Notification
        fields = ["id", "event", "scan_id", "analysis_run_id", "patient_id", "created_at", "read_at"]
        read_only_fields = fields


class NotificationListSerializer(serializers.Serializer):
    unread_count = serializers.IntegerField()
    results = NotificationSerializer(many=True)
