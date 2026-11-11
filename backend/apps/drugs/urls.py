from django.urls import path

from .views import DrugSearchView, ResolveMedicationsView

urlpatterns = [
    path("medications/resolve/", ResolveMedicationsView.as_view(), name="medications-resolve"),
    path("drugs/search/", DrugSearchView.as_view(), name="drugs-search"),
]