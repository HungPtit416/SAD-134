from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..application.chat import answer_chat
from ..application.indexing import index_products
from ..application.recommendation import hydrate_products, recommend_products
from .serializers import ChatRequestSerializer, RecommendationRequestSerializer


@api_view(["GET"])
def recommendations(request):
    ser = RecommendationRequestSerializer(data={"user_id": request.query_params.get("user_id"), "limit": request.query_params.get("limit")})
    ser.is_valid(raise_exception=True)
    user_id = ser.validated_data["user_id"]
    limit = ser.validated_data.get("limit") or 10

    recs = recommend_products(user_id, limit=limit)
    return Response({"user_id": user_id, "items": hydrate_products(recs)})


@api_view(["POST"])
def index(request):
    """
    (Dev/MVP) Build embeddings for product documents into pgvector.
    """

    try:
        res = index_products()
        return Response({"upserted": res.upserted}, status=status.HTTP_200_OK)
    except Exception as e:  # noqa: BLE001
        # Return a clear error instead of Django debug HTML.
        return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["POST"])
def chat(request):
    ser = ChatRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user_id = ser.validated_data["user_id"]
    message = ser.validated_data["message"]

    result = answer_chat(user_id, message)
    return Response({"answer": result.answer, "context": result.context}, status=status.HTTP_200_OK)

