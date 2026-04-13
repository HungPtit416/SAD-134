from django.db import models


class StockItem(models.Model):
    product_id = models.PositiveBigIntegerField(unique=True)
    initial_quantity = models.IntegerField(default=0)
    quantity = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product_id"]

