from rest_framework.routers import SimpleRouter

from .views import FollowUpTaskViewSet

router = SimpleRouter()
router.register("follow-ups", FollowUpTaskViewSet, basename="follow-up")

urlpatterns = router.urls
