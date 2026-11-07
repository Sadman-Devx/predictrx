from django.urls import path

from .views import PatientVitalsView, VitalsIngestView

urlpatterns = [
    path("vitals/ingest/", VitalsIngestView.as_view(), name="vitals-ingest"),
    path("vitals/patient/<str:patient_id>/", PatientVitalsView.as_view(), name="vitals-patient"),
]
