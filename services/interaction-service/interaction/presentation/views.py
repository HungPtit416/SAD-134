from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..infrastructure.models import Event
from .serializers import CreateEventSerializer, EventSerializer


@api_view(["POST"])
def create_event(request):
    ser = CreateEventSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    ev = Event.objects.create(
        user_id=data["user_id"],
        session_id=(data.get("session_id") or None),
        event_type=data["event_type"],
        product_id=data.get("product_id"),
        query=(data.get("query") or None),
        metadata=data.get("metadata") or {},
    )
    return Response(EventSerializer(ev).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def list_events(request):
    qs = Event.objects.all()
    user_id = request.query_params.get("user_id")
    if user_id:
        qs = qs.filter(user_id=user_id)
    event_type = request.query_params.get("event_type")
    if event_type:
        qs = qs.filter(event_type=event_type)
    limit = int(request.query_params.get("limit", "50"))
    limit = max(1, min(5000, limit))
    qs = qs[:limit]
    return Response(EventSerializer(qs, many=True).data)

