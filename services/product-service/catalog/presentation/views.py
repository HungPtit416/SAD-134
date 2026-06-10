from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..application.ratings import upsert_product_review
from ..infrastructure.models import Book, Category, Electronics, Fashion, Product, ProductReview
from .permissions import StaffWritePermission
from .serializers import CategorySerializer, ProductRateSerializer, ProductSerializer


def _get_user_id(request) -> str | None:
    hdr = (request.headers.get("X-User-Id") or "").strip().lower()
    if hdr and hdr != "guest":
        return hdr
    qp = (request.query_params.get("user_id") or "").strip().lower()
    if qp and qp != "guest":
        return qp
    body = request.data.get("user_id") if hasattr(request, "data") else None
    if body is not None:
        s = str(body).strip().lower()
        if s and s != "guest":
            return s
    return None


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [StaffWritePermission]


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [StaffWritePermission]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["user_id"] = _get_user_id(self.request)
        return ctx

    def get_queryset(self):
        qs = (
            Product.objects.select_related("category")
            .select_related("book", "electronics", "fashion")
            .all()
        )
        main = (self.request.query_params.get("main_category") or "").strip().upper()
        if main in {Product.MAIN_CATEGORY_BOOK, Product.MAIN_CATEGORY_ELECTRONICS, Product.MAIN_CATEGORY_FASHION}:
            qs = qs.filter(main_category=main)
        return qs

    @action(detail=True, methods=["post"], url_path="rate", permission_classes=[AllowAny])
    def rate(self, request, pk=None):
        user_id = _get_user_id(request)
        if not user_id:
            return Response({"detail": "Bạn cần đăng nhập để đánh giá."}, status=status.HTTP_401_UNAUTHORIZED)
        product = self.get_object()
        ser = ProductRateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        stars = ser.validated_data["stars"]
        upsert_product_review(user_id=user_id, product_id=product.id, stars=stars)
        product.refresh_from_db()
        data = ProductSerializer(product, context={"user_id": user_id}).data
        return Response(data)

    @action(detail=True, methods=["get"], url_path="my-rating", permission_classes=[AllowAny])
    def my_rating(self, request, pk=None):
        user_id = _get_user_id(request)
        if not user_id:
            return Response({"stars": None})
        review = ProductReview.objects.filter(product_id=pk, user_id=user_id).first()
        return Response({"stars": review.stars if review else None})
