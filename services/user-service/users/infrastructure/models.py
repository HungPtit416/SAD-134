from django.db import models


class Role(models.Model):
    name = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Customer(models.Model):
    user_id = models.CharField(max_length=64, unique=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True, related_name="customers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} ({self.email})"

