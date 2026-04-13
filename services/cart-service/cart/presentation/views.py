from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..application.inventory_gateway import InventoryError, release_stock, reserve_stock
from ..application.product_gateway import fetch_product_snapshot
from ..infrastructure.models import Cart, CartItem
from .serializers import CartItemSerializer, CartSerializer


def _get_user_id(request) -> str | None:
    return request.query_params.get("user_id") or request.headers.get("X-User-Id")


@api_view(["GET"])
def get_cart(request):
    user_id = _get_user_id(request)
    if not user_id:
        return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)
    cart, _ = Cart.objects.get_or_create(user_id=user_id)
    return Response(CartSerializer(cart).data)


@api_view(["POST"])
def add_item(request):
    user_id = _get_user_id(request)
    if not user_id:
        return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)

    product_id = request.data.get("product_id")
    quantity = int(request.data.get("quantity", 1))
    if not product_id or quantity <= 0:
        return Response({"detail": "product_id and quantity are required"}, status=status.HTTP_400_BAD_REQUEST)

    cart, _ = Cart.objects.get_or_create(user_id=user_id)
    snapshot = fetch_product_snapshot(int(product_id))

    with transaction.atomic():
        item, created = CartItem.objects.get_or_create(cart=cart, product_id=int(product_id))
        delta = quantity if created else quantity
        try:
            reserve_stock(int(product_id), int(delta))
        except InventoryError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        if created:
            item.quantity = quantity
        else:
            item.quantity += quantity
        item.unit_price = snapshot.price
        item.currency = snapshot.currency or item.currency
        item.save()

    return Response(CartItemSerializer(item).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
def update_item(request, item_id: int):
    user_id = _get_user_id(request)
    if not user_id:
        return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        cart = Cart.objects.get(user_id=user_id)
        item = CartItem.objects.get(cart=cart, id=item_id)
    except (Cart.DoesNotExist, CartItem.DoesNotExist):
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    qty = request.data.get("quantity")
    if qty is None:
        return Response({"detail": "quantity is required"}, status=status.HTTP_400_BAD_REQUEST)
    qty = int(qty)
    if qty <= 0:
        try:
            release_stock(int(item.product_id), int(item.quantity))
        except Exception:  # noqa: BLE001
            pass
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    delta = qty - int(item.quantity)
    if delta > 0:
        try:
            reserve_stock(int(item.product_id), int(delta))
        except InventoryError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
    elif delta < 0:
        try:
            release_stock(int(item.product_id), int(-delta))
        except Exception:  # noqa: BLE001
            pass

    item.quantity = qty
    item.save()
    return Response(CartItemSerializer(item).data)


@api_view(["DELETE"])
def remove_item(request, item_id: int):
    user_id = _get_user_id(request)
    if not user_id:
        return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        cart = Cart.objects.get(user_id=user_id)
        item = CartItem.objects.get(cart=cart, id=item_id)
    except (Cart.DoesNotExist, CartItem.DoesNotExist):
        return Response(status=status.HTTP_204_NO_CONTENT)

    try:
        release_stock(int(item.product_id), int(item.quantity))
    except Exception:  # noqa: BLE001
        pass
    item.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["DELETE"])
def clear_cart(request):
    user_id = _get_user_id(request)
    if not user_id:
        return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        cart = Cart.objects.get(user_id=user_id)
    except Cart.DoesNotExist:
        return Response(status=status.HTTP_204_NO_CONTENT)

    release = request.query_params.get("release", "1") != "0"
    if release:
        for it in cart.items.all():
            try:
                release_stock(int(it.product_id), int(it.quantity))
            except Exception:  # noqa: BLE001
                pass
    cart.items.all().delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

