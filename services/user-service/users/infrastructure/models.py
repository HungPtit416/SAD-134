from django.db import models


class Customer(models.Model):
    user_id = models.CharField(max_length=64, unique=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} ({self.email})"

