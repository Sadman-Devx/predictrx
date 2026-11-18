from django.urls import path

from .views import EvalDashboardView, EvalRunDetailView, EvalRunListView, EvalRunStartView

urlpatterns = [
    path("eval/run/", EvalRunStartView.as_view(), name="eval-run"),
    path("eval/runs/", EvalRunListView.as_view(), name="eval-run-list"),
    path("eval/runs/<int:pk>/", EvalRunDetailView.as_view(), name="eval-run-detail"),
    path("eval/dashboard/", EvalDashboardView.as_view(), name="eval-dashboard"),
]
