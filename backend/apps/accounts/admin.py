from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from core.admin_base import USER_ADMIN_FORMS, BaseModelAdmin, display

from .models import User


@admin.register(User)
class CustomUserAdmin(DjangoUserAdmin, BaseModelAdmin):
    # Unfold's styled forms when it is installed; Django's own otherwise (core/admin_base.py).
    form = USER_ADMIN_FORMS.get("form", DjangoUserAdmin.form)
    add_form = USER_ADMIN_FORMS.get("add_form", DjangoUserAdmin.add_form)
    change_password_form = USER_ADMIN_FORMS.get("change_password_form", DjangoUserAdmin.change_password_form)

    ordering = ("email",)
    list_display = ("email", "role_badge", "display_name", "email_verified", "is_active")
    list_filter = ("role", "is_active", "email_verified")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("display_name", "role", "preferred_language", "email_verified")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),)
    search_fields = ("email", "display_name")

    @display(description="Role", ordering="role",
             label={"admin": "danger", "doctor": "primary", "pharmacist": "info", "family": "warning"})
    def role_badge(self, obj):
        return obj.role
