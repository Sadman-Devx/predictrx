from django.contrib import admin

from core.admin_base import BaseModelAdmin, PatientDataAdminMixin, display

from .models import AgentTrace, AnalysisRun, RiskFinding, RiskSummary


class SnapshotAdmin(PatientDataAdminMixin, BaseModelAdmin):
    """Runs are snapshots (rule.md §4): visible in admin, never editable or creatable by hand."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AnalysisRun)
class AnalysisRunAdmin(SnapshotAdmin):
    list_display = ("id", "patient", "status_badge", "requested_by", "started_at", "finished_at")
    list_filter = ("status",)
    list_select_related = ("patient", "requested_by")
    exclude = ("input_snapshot",)  # redacted, but still patient context: not needed in a list/detail page

    @display(description="Status", ordering="status",
             label={"completed": "success", "running": "info", "queued": "info", "failed": "danger"})
    def status_badge(self, obj):
        return obj.status


@admin.register(RiskFinding)
class RiskFindingAdmin(SnapshotAdmin):
    list_display = ("id", "run_id", "drug_a", "drug_b", "severity_badge", "verification_badge")
    list_filter = ("severity", "verification_status")
    list_select_related = ("drug_a", "drug_b")

    @display(description="Severity", ordering="severity",
             label={"major": "danger", "moderate": "warning", "minor": "info"})
    def severity_badge(self, obj):
        return obj.severity

    @display(description="Verification", ordering="verification_status",
             label={"verified": "success", "unverified": "warning", "conflict": "danger"})
    def verification_badge(self, obj):
        return obj.verification_status


@admin.register(AgentTrace)
class AgentTraceAdmin(SnapshotAdmin):
    list_display = ("id", "run_id", "agent_name", "step_order", "latency_ms")
    list_filter = ("agent_name",)


@admin.register(RiskSummary)
class RiskSummaryAdmin(SnapshotAdmin):
    list_display = ("id", "run_id", "disclaimer_version")
