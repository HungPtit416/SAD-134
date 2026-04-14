from django.urls import path

from . import views

urlpatterns = [
    path("events/", views.create_event),
    path("events/list/", views.list_events),
]

