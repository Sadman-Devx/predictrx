from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    # drugs before any router that later adds medications/<id>/, so "medications/resolve/" is matched first
    path("api/", include("apps.drugs.urls")),
    path("api/", include("apps.patients.urls")),
    path("api/", include("apps.vitals.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    # TODO (backend dev): clinical, drugs, analysis, twin, family, eval routes (later days)
]