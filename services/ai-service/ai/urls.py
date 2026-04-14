from django.urls import include, path

urlpatterns = [
    path("", include("ai.presentation.urls")),
]

