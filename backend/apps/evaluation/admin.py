import json

from django.contrib import admin
from django.utils.html import format_html, format_html_join

from core.admin_base import BaseModelAdmin, display

from . import metrics as eval_metrics
from .models import EvalCase, EvalRun


def test_split_reported() -> bool:
    return EvalRun.objects.filter(kind="pairs", split="test", status="completed").exists()


class ReviewedFilter(admin.SimpleListFilter):
    title = "reviewed"
    parameter_name = "reviewed"

    def lookups(self, request, model_admin):
        return (("yes", "Has a reviewer"), ("no", "No reviewer"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(reviewed_by="")
        if self.value() == "no":
            return queryset.filter(reviewed_by="")
        return queryset


@admin.register(EvalCase)
class EvalCaseAdmin(BaseModelAdmin):
    """Reviewed labels. After a test run has been reported, test cases (and the label/split of every case) are
    frozen: editing or deleting a hard case after seeing the result is how a test set stops being a test set."""

    list_display = ("id", "drug_a", "drug_b", "expected_badge", "split_badge", "reviewed")
    list_filter = ("split", "expected_severity", ReviewedFilter)
    list_select_related = ("drug_a", "drug_b")
    search_fields = ("drug_a__generic_name", "drug_b__generic_name", "reviewed_by", "rationale_ref")
    autocomplete_fields = ("drug_a", "drug_b")
    list_per_page = 50

    @display(description="Expected", ordering="expected_severity",
             label={"major": "danger", "moderate": "warning", "minor": "info", "none": "success"})
    def expected_badge(self, obj):
        return obj.expected_severity

    @display(description="Split", ordering="split", label={"test": "primary", "dev": "info"})
    def split_badge(self, obj):
        return obj.split

    @display(description="Reviewed", boolean=True)
    def reviewed(self, obj):
        return bool(obj.reviewed_by)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and test_split_reported():
            return ("drug_a", "drug_b", "expected_severity", "split")
        return ()

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.split == "test" and test_split_reported():
            return False
        return super().has_delete_permission(request, obj)


PAIR_ROWS = (
    ("Recall (pairs the reviewer says interact, flagged by the system)", "recall"),
    ("Precision", "precision"),
    ("Specificity", "specificity"),
    ("Severity agreement (among detected pairs)", "severity_agreement"),
    ("Major pairs not called major", "major_not_called_major"),
)
BRAND_ROWS = (
    ("Accuracy", "accuracy"),
    ("Resolved precision", "resolved_precision"),
    ("Coverage of known brands", "coverage_of_known"),
    ("Wrong silent resolutions", "wrong_resolution_rate"),
    ("Answered by exact lookup (circularity indicator)", "exact_lookup_share"),
)


def _pct(rate) -> str:
    value = (rate or {}).get("value")
    return "n/a" if value is None else f"{value:.1%}"


def _pretty(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True, default=str)


@admin.register(EvalRun)
class EvalRunAdmin(BaseModelAdmin):
    """Runs are history (rule.md §4): visible, never editable, creatable or deletable by hand.

    Every number is shown with its n (k/n and 95% interval). Per-case details of the TEST split are never stored,
    so there is nothing here to tune against.
    """

    list_display = ("id", "kind", "split", "status_badge", "n_cases", "headline", "integrity", "created_at",
                    "duration", "created_by")
    list_filter = ("kind", "split", "status")
    list_select_related = ("created_by",)
    ordering = ("-id",)
    readonly_fields = ("kind", "split", "status", "error_code", "n_cases", "created_by", "created_at",
                       "started_at", "finished_at", "fingerprint", "summary", "metrics_json", "config_json")
    fieldsets = (
        ("Run", {"fields": ("kind", "split", "status", "error_code", "n_cases", "fingerprint", "created_by",
                            "created_at", "started_at", "finished_at")}),
        ("Result", {"fields": ("summary", "metrics_json")}),
        ("How it was run", {"fields": ("config_json",)}),
    )

    # ---- list columns
    @display(description="Status", ordering="status",
             label={"completed": "success", "running": "info", "queued": "info", "failed": "danger"})
    def status_badge(self, obj):
        return obj.status

    @display(description="Headline")
    def headline(self, obj):
        if obj.status != "completed" or not obj.metrics:
            return "-"
        if obj.kind == "pairs":
            return (f"recall {_pct(obj.metrics.get('recall'))} - precision {_pct(obj.metrics.get('precision'))} "
                    f"- n={obj.n_cases}")
        return (f"accuracy {_pct(obj.metrics.get('accuracy'))} - wrong {_pct(obj.metrics.get('wrong_resolution_rate'))} "
                f"- n={obj.n_cases}")

    @display(description="Cited", label={"OK": "success", "VIOLATION": "danger"})
    def integrity(self, obj):
        """A severity without a citation must never happen (rule.md §1). VIOLATION = investigate before quoting."""
        if obj.kind != "pairs" or obj.status != "completed" or not obj.metrics:
            return "-"
        return "VIOLATION" if (obj.metrics.get("integrity") or {}).get("severity_without_citation") else "OK"

    @display(description="Duration")
    def duration(self, obj):
        if obj.started_at and obj.finished_at:
            return f"{(obj.finished_at - obj.started_at).total_seconds():.0f}s"
        return "-"

    # ---- detail page
    @display(description="Summary")
    def summary(self, obj):
        if obj.status != "completed" or not obj.metrics:
            return f"No result (status: {obj.status}{', ' + obj.error_code if obj.error_code else ''})."
        spec = PAIR_ROWS if obj.kind == "pairs" else BRAND_ROWS
        rows = [(label, eval_metrics.format_rate(obj.metrics.get(key))) for label, key in spec]
        rows.insert(0, ("Cases (n)", str(obj.n_cases)))
        notes = list(obj.metrics.get("caveats") or []) + list((obj.config or {}).get("caveats") or [])
        if (obj.config or {}).get("test_note"):
            notes.append(obj.config["test_note"])
        table = format_html_join("", "<tr><th style='text-align:left;padding-right:1rem'>{}</th><td>{}</td></tr>", rows)
        caveats = format_html_join("", "<li>{}</li>", ((note,) for note in notes))
        return format_html("<table>{}</table><ul style='margin-top:.5rem'>{}</ul>", table, caveats)

    @display(description="Metrics (raw)")
    def metrics_json(self, obj):
        return format_html("<pre style='white-space:pre-wrap'>{}</pre>", _pretty(obj.metrics))

    @display(description="Config")
    def config_json(self, obj):
        return format_html("<pre style='white-space:pre-wrap'>{}</pre>", _pretty(obj.config))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
