"""Drug admin: the brand-mapping REVIEW workflow lives here.

Rules (docs/rule.md §1, §6):
  * `verified` stays False until a pharmacist / mentor has reviewed the row. A row without a `source` can never be
    verified.
  * Editing what a verified row says (brand, strength, form, drug) switches the verification off again: the earlier
    review did not cover the new content.
  * Every verify / un-verify (form or bulk action) writes an AuditLog row (`brand_review`): who, when, which row.
    That log is the review record; it is shown on the row's page as "Review history".
  * Bulk verification is capped: a row that was not really looked at must not be verified in a hurry.
"""
from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html_join

from apps.audit import services as audit
from apps.audit.models import AuditLog
from core.admin_base import BaseModelAdmin, display

from .models import BrandMapping, Drug, Interaction

MAX_BULK_REVIEW = 25
MAPPING_FIELDS = ("brand_name", "strength", "dosage_form", "drug")


# ------------------------------------------------------------------------------------------------ brand mappings
class ReviewStateFilter(admin.SimpleListFilter):
    title = "review state"
    parameter_name = "review"

    def lookups(self, request, model_admin):
        return (
            ("needs_review", "Needs review (has a source, not verified)"),
            ("verified", "Verified"),
            ("no_source", "No source (cannot be verified)"),
            ("ambiguous", "Same brand points to several generics"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "needs_review":
            return queryset.filter(verified=False).exclude(source="")
        if value == "verified":
            return queryset.filter(verified=True)
        if value == "no_source":
            return queryset.filter(source="")
        if value == "ambiguous":
            several = (BrandMapping.objects.values("brand_name")
                       .annotate(n=Count("drug", distinct=True)).filter(n__gt=1).values("brand_name"))
            return queryset.filter(brand_name__in=several)
        return queryset


class BrandMappingAdminForm(forms.ModelForm):
    class Meta:
        model = BrandMapping
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        source = (cleaned.get("source") or "").strip()
        if cleaned.get("verified") and not source:
            raise forms.ValidationError("A mapping without a source cannot be verified. Record where it came from first.")
        confidence = cleaned.get("confidence")
        if confidence is not None and not 0 <= confidence <= 1:
            self.add_error("confidence", "Confidence must be between 0 and 1.")
        return cleaned


@admin.register(BrandMapping)
class BrandMappingAdmin(BaseModelAdmin):
    form = BrandMappingAdminForm
    list_display = ("brand_name", "strength", "dosage_form", "drug", "review_state", "confidence", "source",
                    "source_accessed")
    list_display_links = ("brand_name",)
    list_filter = (ReviewStateFilter, "dosage_form", "source")
    search_fields = ("brand_name", "drug__generic_name", "source", "source_ref")
    list_select_related = ("drug",)
    autocomplete_fields = ("drug",)
    ordering = ("verified", "brand_name", "strength")  # unreviewed rows first
    list_per_page = 50
    actions = ("mark_verified", "mark_needs_review")
    readonly_fields = ("review_history",)
    fieldsets = (
        ("Mapping", {"fields": ("brand_name", "strength", "dosage_form", "drug")}),
        ("Source (required)", {"fields": ("source", "source_ref", "source_accessed")}),
        ("Review", {
            "fields": ("verified", "confidence", "review_history"),
            "description": "Tick 'verified' only after a pharmacist or mentor has checked this row. "
                           "Changing brand, strength, form or generic switches verification off again.",
        }),
    )

    @display(description="Review", ordering="verified",
             label={"Verified": "success", "Needs review": "warning", "No source": "danger"})
    def review_state(self, obj):
        if not (obj.source or "").strip():
            return "No source"
        return "Verified" if obj.verified else "Needs review"

    @display(description="Review history")
    def review_history(self, obj):
        if obj is None or obj.pk is None:
            return "-"
        entries = (AuditLog.objects.filter(action=audit.BRAND_REVIEW, object_type="BrandMapping",
                                           object_id=str(obj.pk))
                   .select_related("actor").order_by("-at", "-id")[:5])
        rows = [(timezone.localtime(e.at).strftime("%Y-%m-%d %H:%M"), (e.meta or {}).get("change", "?"),
                 e.actor.email if e.actor else "deleted user") for e in entries]
        if not rows:
            return "No review recorded yet."
        return format_html_join("", "<div>{} - {} by {}</div>", rows)

    @staticmethod
    def _record(request, obj, change, **meta):
        audit.record(request, audit.BRAND_REVIEW, obj=obj, change=change, drug_id=obj.drug_id, **meta)

    def save_model(self, request, obj, form, change):
        reset = bool(change and obj.verified and "verified" not in form.changed_data
                     and any(name in form.changed_data for name in MAPPING_FIELDS))
        if reset:
            obj.verified = False
        super().save_model(request, obj, form, change)
        if reset:
            self._record(request, obj, "unverified", via="form", reason="mapping_changed")
            self.message_user(request, "The mapping content changed, so it is no longer verified. "
                                       "Have it reviewed again.", messages.WARNING)
        elif "verified" in form.changed_data:
            self._record(request, obj, "verified" if obj.verified else "unverified", via="form")

    @admin.action(description="Mark selected as VERIFIED (a pharmacist / mentor has checked them)",
                  permissions=["change"])
    def mark_verified(self, request, queryset):
        total = queryset.count()
        if total > MAX_BULK_REVIEW:
            self.message_user(request, f"Select at most {MAX_BULK_REVIEW} rows at a time: every row must really "
                                       "be reviewed.", messages.ERROR)
            return
        done = no_source = 0
        with transaction.atomic():
            for row in queryset.filter(verified=False):
                if not (row.source or "").strip():
                    no_source += 1
                    continue
                row.verified = True
                row.save(update_fields=["verified"])
                self._record(request, row, "verified", via="bulk_action")
                done += 1
        if done:
            self.message_user(request, f"{done} mapping(s) marked as verified.", messages.SUCCESS)
        if no_source:
            self.message_user(request, f"{no_source} mapping(s) skipped: no source recorded.", messages.WARNING)
        already = total - done - no_source
        if already:
            self.message_user(request, f"{already} mapping(s) were already verified.", messages.INFO)

    @admin.action(description="Mark selected as NEEDS REVIEW (remove verification)", permissions=["change"])
    def mark_needs_review(self, request, queryset):
        done = 0
        with transaction.atomic():
            for row in queryset.filter(verified=True):
                row.verified = False
                row.save(update_fields=["verified"])
                self._record(request, row, "unverified", via="bulk_action")
                done += 1
        self.message_user(request, f"{done} mapping(s) are back to 'needs review'.", messages.SUCCESS)


# ------------------------------------------------------------------------------------------------ drugs
@admin.register(Drug)
class DrugAdmin(BaseModelAdmin):
    list_display = ("generic_name", "brand_count")
    search_fields = ("generic_name",)  # also used by the autocomplete fields of other admins
    ordering = ("generic_name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_brand_total=Count("brands", distinct=True))

    @display(description="Brand rows", ordering="_brand_total")
    def brand_count(self, obj):
        return obj._brand_total


# ------------------------------------------------------------------------------------------------ interactions
class InteractionAdminForm(forms.ModelForm):
    class Meta:
        model = Interaction
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        a, b = cleaned.get("drug_a"), cleaned.get("drug_b")
        if a and b:
            if a.pk == b.pk:
                raise forms.ValidationError("An interaction needs two different drugs.")
            if a.pk > b.pk:  # stored in canonical order (drug_a.id < drug_b.id)
                cleaned["drug_a"], cleaned["drug_b"] = b, a
        return cleaned


@admin.register(Interaction)
class InteractionAdmin(BaseModelAdmin):
    form = InteractionAdminForm
    list_display = ("drug_a", "drug_b", "severity_badge", "source", "license_note")
    list_filter = ("severity", "source")
    search_fields = ("drug_a__generic_name", "drug_b__generic_name", "source")
    list_select_related = ("drug_a", "drug_b")
    autocomplete_fields = ("drug_a", "drug_b")
    list_per_page = 50
    show_full_result_count = False  # the interaction table is large: no COUNT(*) on every page

    @display(description="Severity", ordering="severity",
             label={"major": "danger", "moderate": "warning", "minor": "info"})
    def severity_badge(self, obj):
        return obj.severity
