from django.contrib import admin

from core.admin_base import BaseModelAdmin, display

from .models import Device, VitalReading


@admin.register(Device)
class DeviceAdmin(BaseModelAdmin):
    list_display = ("device_id", "is_active", "created_at")


@admin.register(VitalReading)
class VitalReadingAdmin(BaseModelAdmin):
    list_display = ("patient_id", "spo2", "pulse", "severity_badge", "source", "recorded_at")
    list_filter = ("severity", "source")

    @display(description="Severity", ordering="severity", label={"critical": "danger", "warning": "warning", "normal": "success"})
    def severity_badge(self, obj):
        return obj.severity
