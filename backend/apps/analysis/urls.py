from django.urls import path

from .views import AnalysisDetailView, AnalysisPatientCardView, AnalysisStartView, AnalysisTraceView

urlpatterns = [
    path("analysis/", AnalysisStartView.as_view(), name="analysis-start"),
    path("analysis/<int:pk>/", AnalysisDetailView.as_view(), name="analysis-detail"),
    path("analysis/<int:pk>/trace/", AnalysisTraceView.as_view(), name="analysis-trace"),
    path("analysis/<int:pk>/patient-card/", AnalysisPatientCardView.as_view(), name="analysis-patient-card"),
]