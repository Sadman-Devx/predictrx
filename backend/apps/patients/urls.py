from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import MedicationViewSet, PatientViewSet

router = SimpleRouter()
router.register("patients", PatientViewSet, basename="patient")

# Nested route: /patients/{patient_pk}/medications/
medication_router = SimpleRouter()
medication_router.register("medications", MedicationViewSet, basename="patient-medication")

urlpatterns = [
    *router.urls,
    path("patients/<int:patient_pk>/", include(medication_router.urls)),
]
