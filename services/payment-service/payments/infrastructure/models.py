from django.db import models


class Payment(models.Model):
    """
    Mock payment record for the course project.
    """

    user_id = models.CharField(max_length=64)
    order_id = models.PositiveBigIntegerField(db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=32, default="AUTHORIZED")  # AUTHORIZED -> CAPTURED/FAILED
    provider = models.CharField(max_length=32, default="mock")
    reference = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

