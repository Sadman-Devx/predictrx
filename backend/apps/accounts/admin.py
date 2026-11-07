from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "role", "display_name", "is_active")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("display_name", "role", "preferred_language")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),)
    search_fields = ("email", "display_name")
