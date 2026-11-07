from django.contrib import admin

from .models import Device, VitalReading


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "is_active", "created_at")


@admin.register(VitalReading)
class VitalReadingAdmin(admin.ModelAdmin):
    list_display = ("patient_id", "spo2", "pulse", "severity", "source", "recorded_at")
    list_filter = ("severity", "source")
