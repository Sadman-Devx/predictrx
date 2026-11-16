from django.contrib import admin

from core.admin_base import BaseModelAdmin, PatientDataAdminMixin, display

from .models import ClinicalNote, LabResult, Medication, PrescriptionScan


@admin.register(PrescriptionScan)
class PrescriptionScanAdmin(PatientDataAdminMixin, BaseModelAdmin):
    """Scans are shown WITHOUT the image: the file is private (no URL exists), so the default file widget would crash.

    Admins see status, error code, retention and the draft summary only; nobody can add or edit a scan here.
    """

    list_display = ("id", "patient", "status_badge", "error_code", "content_type", "retain_until", "image_deleted_at",
                    "created_at")
    list_filter = ("status", "error_code")
    list_select_related = ("patient",)
    exclude = ("image",)
    readonly_fields = ("patient", "content_type", "image_sha256", "status", "error_code", "extracted_json",
                       "retain_until", "image_deleted_at", "created_at")

    @display(description="Status", ordering="status",
             label={"extracted": "success", "processing": "info", "queued": "info", "failed": "danger"})
    def status_badge(self, obj):
        return obj.status

    def has_add_permission(self, request):
        return False


@admin.register(Medication)
class MedicationAdmin(PatientDataAdminMixin, BaseModelAdmin):
    list_display = ("id", "patient", "raw_text", "drug", "resolution_badge", "confirmed_by_user", "source", "created_at")
    list_filter = ("source", "resolution_status", "confirmed_by_user")
    list_select_related = ("patient", "drug")
    raw_id_fields = ("patient", "scan", "drug")

    @display(description="Resolution", ordering="resolution_status",
             label={"resolved": "success", "user_confirmed": "info", "unresolved": "warning"})
    def resolution_badge(self, obj):
        return obj.resolution_status


@admin.register(LabResult)
class LabResultAdmin(PatientDataAdminMixin, BaseModelAdmin):
    list_display = ("id", "patient", "test_name", "value", "unit", "recorded_at")
    list_select_related = ("patient",)
    raw_id_fields = ("patient",)
    search_fields = ("test_name", "patient__patient_code")


@admin.register(ClinicalNote)
class ClinicalNoteAdmin(PatientDataAdminMixin, BaseModelAdmin):
    """The list never shows note text (free text about a patient): open one record to read it (audited)."""

    list_display = ("id", "patient", "created_at")
    list_select_related = ("patient",)
    raw_id_fields = ("patient",)
