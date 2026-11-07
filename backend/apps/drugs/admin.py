from django.contrib import admin

from .models import BrandMapping, Drug, Interaction


@admin.register(BrandMapping)
class BrandMappingAdmin(admin.ModelAdmin):
    list_display = ("brand_name", "strength", "drug", "source", "verified", "confidence")
    list_filter = ("verified",)
    search_fields = ("brand_name", "drug__generic_name")


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    search_fields = ("generic_name",)


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ("drug_a", "drug_b", "severity", "source")
    list_filter = ("severity", "source")
