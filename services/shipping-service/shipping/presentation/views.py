from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..infrastructure.models import Shipment
from .serializers import CreateShipmentRequestSerializer, ShipmentSerializer


@api_view(["GET"])
def ping(request):
    return Response({"ok": True, "service": "shipping-service"})


@api_view(["GET"])
def rates(request):
    """
    Minimal shipping rates endpoint for checkout UI.
    Fees are in VND and can be extended later to use address/weight.
    """

    return Response(
        {
            "currency": "VND",
            "methods": [
                {"code": "STANDARD", "name": "Standard (3-5 days)", "fee": 30000},
                {"code": "EXPRESS", "name": "Express (1-2 days)", "fee": 60000},
                {"code": "SAME_DAY", "name": "Same day (within city)", "fee": 120000},
            ],
        }
    )


@api_view(["GET"])
def list_shipments(request):
    user_id = request.query_params.get("user_id")
    order_id = request.query_params.get("order_id")
    qs = Shipment.objects.all()
    if user_id:
        qs = qs.filter(user_id=user_id)
    if order_id:
        try:
            qs = qs.filter(order_id=int(order_id))
        except Exception:  # noqa: BLE001
            pass
    return Response(ShipmentSerializer(list(qs[:200]), many=True).data)


@api_view(["POST"])
def create_shipment(request):
    ser = CreateShipmentRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user_id = ser.validated_data["user_id"]
    order_id = int(ser.validated_data["order_id"])
    address = (ser.validated_data.get("address") or "").strip()

    tracking = f"TRK-{order_id}-{pseudoref(order_id)}"
    sh = Shipment.objects.create(
        user_id=user_id,
        order_id=order_id,
        status="CREATED",
        carrier="mock",
        tracking_code=tracking,
        address=address,
    )
    return Response(ShipmentSerializer(sh).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def update_status(request, shipment_id: int):
    try:
        sh = Shipment.objects.get(id=shipment_id)
    except Shipment.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    nxt = str(request.data.get("status") or "").strip().upper()
    allowed = {"CREATED", "IN_TRANSIT", "DELIVERED", "CANCELLED"}
    if nxt not in allowed:
        return Response({"detail": f"Invalid status (allowed: {sorted(allowed)})"}, status=status.HTTP_400_BAD_REQUEST)
    sh.status = nxt
    sh.save(update_fields=["status"])
    return Response(ShipmentSerializer(sh).data)


def pseudoref(order_id: int) -> str:
    s = hex((order_id * 2246822519) & 0xFFFFFFFF)[2:]
    return s[-8:].upper()

