from django.urls import path

from .views import TwinDetailView, TwinListView, TwinStartView

urlpatterns = [
    path("twin/", TwinStartView.as_view(), name="twin-start"),
    path("twin/<int:pk>/", TwinDetailView.as_view(), name="twin-detail"),
    path("analysis/<int:pk>/twin/", TwinListView.as_view(), name="twin-list"),
]
