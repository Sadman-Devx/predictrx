"""Admin building blocks shared by every app's admin.py.

* Reskin: when `django-unfold` is installed (requirements/base.txt) every ModelAdmin inherits Unfold's ModelAdmin.
  If it is missing, everything falls back to the plain Django admin (roadmap cut order), so a missing package can
  never take the admin down.
* Audit: opening patient data in the admin is a patient-data read like any other, so it writes an AuditLog row
  (docs/rule.md §3). The write happens inside the admin's own transaction: if it fails, the page is not shown.
"""
from django.apps import apps
from django.contrib import admin

UNFOLD_ENABLED = apps.is_installed("unfold")

if UNFOLD_ENABLED:
    from unfold.admin import ModelAdmin as BaseModelAdmin
    from unfold.decorators import display
    from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

    USER_ADMIN_FORMS = {
        "form": UserChangeForm,
        "add_form": UserCreationForm,
        "change_password_form": AdminPasswordChangeForm,
    }
else:
    BaseModelAdmin = admin.ModelAdmin
    USER_ADMIN_FORMS = {}

    def display(function=None, *, description=None, ordering=None, boolean=None, **_unfold_only):
        """Plain-admin stand-in for unfold's @display (label / header / dropdown are Unfold-only and ignored)."""

        def decorator(func):
            return admin.display(description=description, ordering=ordering, boolean=boolean)(func)

        return decorator(function) if function is not None else decorator


def patient_of(obj):
    """The patient a record belongs to (or None): the object itself, `.patient`, or `.run.patient`."""
    from apps.patients.models import Patient

    if isinstance(obj, Patient):
        return obj
    patient = getattr(obj, "patient", None)
    if patient is not None:
        return patient
    run = getattr(obj, "run", None)
    return getattr(run, "patient", None) if run is not None else None


class PatientDataAdminMixin:
    """Put FIRST in the bases of a ModelAdmin whose rows are patient data.

    Opening one record writes `admin_record_read`, opening the list writes `admin_list_read` (ids only, never
    values, in `meta`).
    """

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if change and obj is not None:
            from apps.audit import services as audit

            audit.record(request, audit.ADMIN_RECORD_READ, patient=patient_of(obj), obj=obj,
                         model=obj._meta.label_lower)
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        if request.method == "GET" and getattr(response, "status_code", 200) == 200:
            from apps.audit import services as audit

            audit.record(request, audit.ADMIN_LIST_READ, model=self.model._meta.label_lower)
        return response
