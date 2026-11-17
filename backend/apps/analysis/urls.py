from django.urls import path

from .views import AnalysisDetailView, AnalysisListView, AnalysisPatientCardView, AnalysisStartView, AnalysisTraceView

urlpatterns = [
    path("analysis/", AnalysisStartView.as_view(), name="analysis-start"),
    path("analysis/runs/", AnalysisListView.as_view(), name="analysis-list"),
    path("analysis/<int:pk>/", AnalysisDetailView.as_view(), name="analysis-detail"),
    path("analysis/<int:pk>/trace/", AnalysisTraceView.as_view(), name="analysis-trace"),
    path("analysis/<int:pk>/patient-card/", AnalysisPatientCardView.as_view(), name="analysis-patient-card"),
]