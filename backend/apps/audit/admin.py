from django.contrib import admin

from core.admin_base import BaseModelAdmin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(BaseModelAdmin):
    """The audit trail is append-only: nobody can add, edit or delete entries through the admin."""

    list_display = ("at", "actor", "action", "patient", "object_type", "object_id")
    list_filter = ("action",)
    search_fields = ("actor__email", "action", "object_id", "patient__patient_code")
    list_select_related = ("actor", "patient")
    date_hierarchy = "at"
    show_full_result_count = False  # the log only grows: no COUNT(*) on every page
    list_per_page = 50
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
