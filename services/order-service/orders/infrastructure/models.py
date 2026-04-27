from django.db import models


class Order(models.Model):
    user_id = models.CharField(max_length=64)
    status = models.CharField(max_length=32, default="CREATED")
    payment_status = models.CharField(max_length=32, default="PENDING")
    payment_id = models.PositiveBigIntegerField(null=True, blank=True)
    inventory_status = models.CharField(max_length=32, default="PENDING")
    shipping_status = models.CharField(max_length=32, default="PENDING")
    shipment_id = models.PositiveBigIntegerField(null=True, blank=True)
    tracking_code = models.CharField(max_length=64, blank=True, default="")
    shipping_address = models.JSONField(default=dict, blank=True)
    shipping_method = models.CharField(max_length=32, blank=True, default="")
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order({self.id}, user={self.user_id}, status={self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product_id = models.PositiveBigIntegerField()
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

