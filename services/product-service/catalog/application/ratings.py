from django.db.models import Avg, Count

from ..infrastructure.models import Product, ProductReview


def refresh_product_ratings(product_id: int) -> None:
    agg = ProductReview.objects.filter(product_id=product_id).aggregate(
        avg=Avg("stars"),
        count=Count("id"),
    )
    avg = float(agg["avg"] or 0)
    count = int(agg["count"] or 0)
    Product.objects.filter(pk=product_id).update(
        ratings=round(avg, 2) if count else 0,
        no_of_ratings=count,
    )


def upsert_product_review(*, user_id: str, product_id: int, stars: int) -> ProductReview:
    review, _ = ProductReview.objects.update_or_create(
        user_id=user_id,
        product_id=product_id,
        defaults={"stars": stars},
    )
    refresh_product_ratings(product_id)
    return review
