from django.urls import path

from .views import CheckInteractionsView, DrugSearchView, ResolveMedicationsView

urlpatterns = [
    path("drugs/search/", DrugSearchView.as_view(), name="drug-search"),
    path("medications/resolve/", ResolveMedicationsView.as_view(), name="medications-resolve"),
    path("interactions/check/", CheckInteractionsView.as_view(), name="interactions-check"),
]