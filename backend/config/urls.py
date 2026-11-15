from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# JSON (not HTML) 404 / 500 for anything under /api/  -> same error shape everywhere. See core/views.py.
handler404 = "core.views.api_not_found"
handler500 = "core.views.api_server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.patients.urls")),
    path("api/", include("apps.clinical.urls")),  # Day 8: prescription scan + medication confirm
    path("api/", include("apps.drugs.urls")),
    path("api/", include("apps.analysis.urls")),
    path("api/", include("apps.vitals.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    # TODO (backend dev): twin, family, eval routes (Day 9-10)
]