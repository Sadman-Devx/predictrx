from django.contrib import admin

from .models import EvalCase, EvalRun


def test_split_reported() -> bool:
    return EvalRun.objects.filter(kind="pairs", split="test", status="completed").exists()


@admin.register(EvalCase)
class EvalCaseAdmin(admin.ModelAdmin):
    """Reviewed labels. After a test run has been reported, test cases (and the label/split of every case) are
    frozen: editing or deleting a hard case after seeing the result is how a test set stops being a test set."""

    list_display = ("id", "drug_a", "drug_b", "expected_severity", "split", "reviewed_by")
    list_filter = ("split", "expected_severity")
    list_select_related = ("drug_a", "drug_b")
    search_fields = ("drug_a__generic_name", "drug_b__generic_name", "reviewed_by", "rationale_ref")
    raw_id_fields = ("drug_a", "drug_b")

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and test_split_reported():
            return ("drug_a", "drug_b", "expected_severity", "split")
        return ()

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.split == "test" and test_split_reported():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(EvalRun)
class EvalRunAdmin(admin.ModelAdmin):
    """Runs are history (rule.md §4): visible, never editable, creatable or deletable by hand."""

    list_display = ("id", "kind", "split", "status", "n_cases", "created_at", "finished_at")
    list_filter = ("kind", "split", "status")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False