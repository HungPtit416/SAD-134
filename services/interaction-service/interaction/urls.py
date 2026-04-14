from django.urls import include, path

urlpatterns = [
    path("", include("interaction.presentation.urls")),
]

