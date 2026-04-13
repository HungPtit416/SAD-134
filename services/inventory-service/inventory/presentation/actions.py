from django.db import transaction
from django.db.models import F
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..infrastructure.models import StockItem
from .serializers import StockItemSerializer


@api_view(["GET"])
def stock_by_products(request):
    ids = request.query_params.get("ids", "").strip()
    if not ids:
        return Response({"detail": "Missing ids"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        product_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        return Response({"detail": "Invalid ids"}, status=status.HTTP_400_BAD_REQUEST)

    items = StockItem.objects.filter(product_id__in=product_ids).order_by("product_id")
    return Response(StockItemSerializer(items, many=True).data)


@api_view(["POST"])
def reserve_stock(request):
    product_id = request.data.get("product_id")
    qty = request.data.get("quantity")
    if product_id is None or qty is None:
        return Response({"detail": "product_id and quantity are required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        product_id = int(product_id)
        qty = int(qty)
    except ValueError:
        return Response({"detail": "Invalid product_id or quantity"}, status=status.HTTP_400_BAD_REQUEST)
    if qty <= 0:
        return Response({"detail": "quantity must be > 0"}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        item, _ = StockItem.objects.select_for_update().get_or_create(
            product_id=product_id, defaults={"initial_quantity": 0, "quantity": 0}
        )
        if item.quantity < qty:
            return Response(
                {"detail": "Insufficient stock", "available": item.quantity},
                status=status.HTTP_409_CONFLICT,
            )
        StockItem.objects.filter(id=item.id).update(quantity=F("quantity") - qty)
        item.refresh_from_db()
    return Response(StockItemSerializer(item).data)


@api_view(["POST"])
def release_stock(request):
    product_id = request.data.get("product_id")
    qty = request.data.get("quantity")
    if product_id is None or qty is None:
        return Response({"detail": "product_id and quantity are required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        product_id = int(product_id)
        qty = int(qty)
    except ValueError:
        return Response({"detail": "Invalid product_id or quantity"}, status=status.HTTP_400_BAD_REQUEST)
    if qty <= 0:
        return Response({"detail": "quantity must be > 0"}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        item, _ = StockItem.objects.select_for_update().get_or_create(
            product_id=product_id, defaults={"initial_quantity": 0, "quantity": 0}
        )
        StockItem.objects.filter(id=item.id).update(quantity=F("quantity") + qty)
        item.refresh_from_db()
    return Response(StockItemSerializer(item).data)

