from django.contrib import admin

from .models import ClinicalNote, LabResult, Medication, PrescriptionScan


@admin.register(PrescriptionScan)
class PrescriptionScanAdmin(admin.ModelAdmin):
    """Scans are shown WITHOUT the image: the file is private (no URL exists), so the default file widget would crash.

    Admins see status, error code, retention and the draft summary only; nobody can add or edit a scan here.
    """

    list_display = ("id", "patient", "status", "error_code", "content_type", "retain_until", "image_deleted_at", "created_at")
    list_filter = ("status", "error_code")
    list_select_related = ("patient",)
    exclude = ("image",)
    readonly_fields = ("patient", "content_type", "image_sha256", "status", "error_code", "extracted_json",
                       "retain_until", "image_deleted_at", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "raw_text", "drug", "resolution_status", "confirmed_by_user", "source", "created_at")
    list_filter = ("source", "resolution_status", "confirmed_by_user")
    list_select_related = ("patient", "drug")
    raw_id_fields = ("patient", "scan", "drug")


admin.site.register([LabResult, ClinicalNote])