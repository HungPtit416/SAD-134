from django.urls import path

from . import views

urlpatterns = [
    path("cart/", views.get_cart),
    path("cart/items/", views.add_item),
    path("cart/items/<int:item_id>/", views.update_item),
    path("cart/items/<int:item_id>/remove/", views.remove_item),
    path("cart/clear/", views.clear_cart),
]

