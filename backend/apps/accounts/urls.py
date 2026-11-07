from django.urls import path

from .views import LoginView, LogoutView, MeView, RefreshView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", RefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    # TODO (backend dev): register (doctor/pharmacist), family invite
]
