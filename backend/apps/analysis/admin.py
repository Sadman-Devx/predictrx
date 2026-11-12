from django.contrib import admin

from .models import AgentTrace, AnalysisRun, RiskFinding, RiskSummary


class SnapshotAdmin(admin.ModelAdmin):
    """Runs are snapshots (rule.md §4): visible in admin, never editable or creatable by hand."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AnalysisRun)
class AnalysisRunAdmin(SnapshotAdmin):
    list_display = ("id", "patient", "status", "requested_by", "started_at", "finished_at")
    list_filter = ("status",)
    exclude = ("input_snapshot",)  # redacted, but still patient context: not needed in a list/detail page


@admin.register(RiskFinding)
class RiskFindingAdmin(SnapshotAdmin):
    list_display = ("id", "run", "drug_a", "drug_b", "severity", "verification_status")
    list_filter = ("severity", "verification_status")


admin.site.register([AgentTrace, RiskSummary], SnapshotAdmin)