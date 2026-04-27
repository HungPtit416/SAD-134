from django.db import models


class Shipment(models.Model):
    user_id = models.CharField(max_length=64)
    order_id = models.PositiveBigIntegerField(db_index=True)
    status = models.CharField(max_length=32, default="CREATED")  # CREATED -> IN_TRANSIT -> DELIVERED
    carrier = models.CharField(max_length=32, default="mock")
    tracking_code = models.CharField(max_length=64, db_index=True)
    address = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

