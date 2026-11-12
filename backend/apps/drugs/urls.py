from django.urls import path

from .interaction_views import InteractionCheckView, InteractionDetailView, InteractionListView
from .views import DrugDetailView, DrugListView, DrugSearchView, ResolveMedicationsView

urlpatterns = [
    path("medications/resolve/", ResolveMedicationsView.as_view(), name="medications-resolve"),
    path("drugs/", DrugListView.as_view(), name="drug-list"),
    path("drugs/<int:pk>/", DrugDetailView.as_view(), name="drug-detail"),
    path("drugs/search/", DrugSearchView.as_view(), name="drugs-search"),
    path("interactions/", InteractionListView.as_view(), name="interaction-list"),
    path("interactions/check/", InteractionCheckView.as_view(), name="interactions-check"),
    path("interactions/<int:pk>/", InteractionDetailView.as_view(), name="interaction-detail"),
]
