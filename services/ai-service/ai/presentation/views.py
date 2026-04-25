from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..application.chat import answer_chat
from ..application.indexing import index_products
from ..application.recommendation import hydrate_products, recommend_products
from ..application.sequence_predictor import predict_next_action
from .serializers import ChatRequestSerializer, RecommendationRequestSerializer


@api_view(["GET"])
def recommendations(request):
    ser = RecommendationRequestSerializer(
        data={
            "user_id": request.query_params.get("user_id"),
            "limit": request.query_params.get("limit"),
            "query": request.query_params.get("query"),
            "seed_product_ids": request.query_params.get("seed_product_ids"),
        }
    )
    ser.is_valid(raise_exception=True)
    user_id = ser.validated_data["user_id"]
    limit = ser.validated_data.get("limit") or 10
    q = (ser.validated_data.get("query") or "").strip() or None
    seed_raw = (ser.validated_data.get("seed_product_ids") or "").strip()
    seed_ids: list[int] = []
    if seed_raw:
        for part in seed_raw.split(","):
            s = part.strip()
            if not s:
                continue
            try:
                seed_ids.append(int(s))
            except Exception:  # noqa: BLE001
                continue
    seed_ids = seed_ids[:50]

    recs = recommend_products(user_id, limit=limit, query=q, seed_product_ids=seed_ids or None)
    pred = predict_next_action(user_id, seq_len=6)
    return Response(
        {
            "user_id": user_id,
            "predicted_next_action": {"enabled": pred.enabled, "action": pred.action, "confidence": pred.confidence, "top_probs": pred.probs, "note": pred.note},
            "query": q,
            "seed_product_ids": seed_ids,
            "items": hydrate_products(recs),
        }
    )


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

