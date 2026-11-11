from django.urls import path

from .interaction_views import InteractionCheckView, InteractionDetailView
from .views import DrugSearchView, ResolveMedicationsView

urlpatterns = [
    path("medications/resolve/", ResolveMedicationsView.as_view(), name="medications-resolve"),
    path("drugs/search/", DrugSearchView.as_view(), name="drugs-search"),
    path("interactions/check/", InteractionCheckView.as_view(), name="interactions-check"),
    path("interactions/<int:pk>/", InteractionDetailView.as_view(), name="interaction-detail"),
]
