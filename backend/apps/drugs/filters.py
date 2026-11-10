from django_filters import rest_framework as filters

from . import services
from .models import Drug, Interaction


class DrugFilter(filters.FilterSet):
    search = filters.CharFilter(method="filter_search", help_text="Case-insensitive match inside the generic name.")

    class Meta:
        model = Drug
        fields: list[str] = []

    def filter_search(self, queryset, name, value):
        value = (value or "").strip().lower()
        return queryset.filter(generic_name__icontains=value) if value else queryset


class InteractionFilter(filters.FilterSet):
    severity = filters.ChoiceFilter(choices=Interaction.SEVERITY)
    source = filters.CharFilter(method="filter_source", help_text="Exact source key, e.g. ddinter.")
    drug = filters.NumberFilter(method="filter_drug", help_text="Drug id. Matches either side of the pair.")

    class Meta:
        model = Interaction
        fields: list[str] = []

    def filter_source(self, queryset, name, value):
        value = (value or "").strip().lower()
        return queryset.filter(source=value) if value else queryset

    def filter_drug(self, queryset, name, value):
        return services.involving_drug(queryset, int(value)) if value is not None else queryset