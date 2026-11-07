from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("at", "actor", "action", "patient", "object_type", "object_id")
    list_filter = ("action",)
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
