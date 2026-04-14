from django.db import models


class Event(models.Model):
    """
    A single user interaction event emitted by frontend/backend.
    """

    user_id = models.CharField(max_length=64, db_index=True)
    session_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    event_type = models.CharField(max_length=64, db_index=True)
    product_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    query = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Event({self.event_type}, user={self.user_id})"

