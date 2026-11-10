from rest_framework.routers import SimpleRouter

from .views import DrugViewSet, InteractionViewSet

router = SimpleRouter()
router.register("drugs", DrugViewSet, basename="drug")
router.register("interactions", InteractionViewSet, basename="interaction")

urlpatterns = router.urls