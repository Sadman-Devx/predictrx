from rest_framework.routers import SimpleRouter

from .views import PatientViewSet

router = SimpleRouter()
router.register("patients", PatientViewSet, basename="patient")

urlpatterns = router.urls
# Consents, family links and /patients/{id}/medications/ are added in later days (see roadmap).