from django.urls import path

from .views import MedicationDetailView, ScanDetailView, ScanImageView, ScanUploadView

urlpatterns = [
    path("prescriptions/scan/", ScanUploadView.as_view(), name="scan-upload"),
    path("prescriptions/scan/<int:pk>/", ScanDetailView.as_view(), name="scan-detail"),
    path("prescriptions/scan/<int:pk>/image/", ScanImageView.as_view(), name="scan-image"),
    path("medications/<int:pk>/", MedicationDetailView.as_view(), name="medication-detail"),
]