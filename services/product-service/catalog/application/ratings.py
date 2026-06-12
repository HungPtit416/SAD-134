from django.db.models import Avg, Count

from ..infrastructure.models import Product, ProductRating


def refresh_product_ratings(product_id: int) -> None:
    agg = ProductRating.objects.filter(product_id=product_id).aggregate(
        avg=Avg("stars"),
        count=Count("id"),
    )
    avg = float(agg["avg"] or 0)
    count = int(agg["count"] or 0)
    Product.objects.filter(pk=product_id).update(
        ratings=round(avg, 2) if count else 0,
        no_of_ratings=count,
    )


def upsert_product_rating(*, user_id: int, product_id: int, stars: int) -> ProductRating:
    rating, _ = ProductRating.objects.update_or_create(
        user_id=user_id,
        product_id=product_id,
        defaults={"stars": stars},
    )
    refresh_product_ratings(product_id)
    return rating
