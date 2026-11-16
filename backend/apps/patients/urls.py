from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .family_views import FamilyPatientListView, FamilyPatientSummaryView
from .views import (
    ConsentBannerView,
    ConsentListCreateView,
    ConsentRevokeView,
    FamilyLinkDetailView,
    FamilyLinkListCreateView,
    MedicationViewSet,
    PatientViewSet,
)

router = SimpleRouter()
router.register("patients", PatientViewSet, basename="patient")

# Nested route: /patients/{patient_pk}/medications/
medication_router = SimpleRouter()
medication_router.register("medications", MedicationViewSet, basename="patient-medication")

urlpatterns = [
    *router.urls,
    # Day 9 — consent (owner: doctor / pharmacist)
    path("patients/<int:patient_pk>/consents/", ConsentListCreateView.as_view(), name="patient-consents"),
    path("patients/<int:patient_pk>/consents/<int:pk>/revoke/", ConsentRevokeView.as_view(),
         name="patient-consent-revoke"),
    # Day 10 — consent banner data (owner: doctor / pharmacist)
    path("patients/<int:patient_pk>/consent-banner/", ConsentBannerView.as_view(), name="patient-consent-banner"),
    # Day 9 — family links (owner: doctor / pharmacist)
    path("patients/<int:patient_pk>/family/", FamilyLinkListCreateView.as_view(), name="patient-family"),
    path("patients/<int:patient_pk>/family/<int:pk>/", FamilyLinkDetailView.as_view(), name="patient-family-detail"),
    # Day 9 — family (NRB) read-only view (role: family)
    path("family/patients/", FamilyPatientListView.as_view(), name="family-patients"),
    path("family/patients/<int:pk>/summary/", FamilyPatientSummaryView.as_view(), name="family-patient-summary"),
    path("patients/<int:patient_pk>/", include(medication_router.urls)),
]