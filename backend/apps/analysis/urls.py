from django.urls import path

from .views import AnalysisDetailView, AnalysisStartView

urlpatterns = [
    path("analysis/", AnalysisStartView.as_view(), name="analysis-start"),
    path("analysis/<int:pk>/", AnalysisDetailView.as_view(), name="analysis-detail"),
]