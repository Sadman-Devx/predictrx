from django.contrib import admin

from core.admin_base import BaseModelAdmin, PatientDataAdminMixin

from .models import TwinScenario


@admin.register(TwinScenario)
class TwinScenarioAdmin(PatientDataAdminMixin, BaseModelAdmin):
    list_display = ("id", "patient", "hypothetical_drug", "created_at")
    list_select_related = ("patient", "hypothetical_drug")
    raw_id_fields = ("patient", "base_run", "hypothetical_drug")
