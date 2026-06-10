from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    tag = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    MAIN_CATEGORY_BOOK = "BOOK"
    MAIN_CATEGORY_ELECTRONICS = "ELECTRONICS"
    MAIN_CATEGORY_FASHION = "FASHION"
    MAIN_CATEGORY_CHOICES = [
        (MAIN_CATEGORY_BOOK, "Book"),
        (MAIN_CATEGORY_ELECTRONICS, "Electronics"),
        (MAIN_CATEGORY_FASHION, "Fashion"),
    ]

    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    image = models.URLField(max_length=1024, blank=True, null=True)
    main_category = models.CharField(max_length=32, choices=MAIN_CATEGORY_CHOICES, default=MAIN_CATEGORY_ELECTRONICS)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    ratings = models.FloatField(default=0)
    no_of_ratings = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.sku} - {self.name}"


class ProductReview(models.Model):
    user_id = models.CharField(max_length=128, db_index=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    stars = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user_id", "product"], name="uniq_product_review_per_user"),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Review(user={self.user_id}, product={self.product_id}, stars={self.stars})"


class Book(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="book")
    author = models.CharField(max_length=255, blank=True, default="")
    publisher = models.CharField(max_length=255, blank=True, default="")
    isbn = models.CharField(max_length=32, blank=True, default="")
    language = models.CharField(max_length=64, blank=True, default="")

    def __str__(self) -> str:
        return f"Book: {self.product.name}"


class Electronics(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="electronics")
    brand = models.CharField(max_length=120, blank=True, default="")
    color = models.CharField(max_length=64, blank=True, default="")
    warranty_months = models.PositiveIntegerField(blank=True, null=True)

    def __str__(self) -> str:
        return f"Electronics: {self.product.name}"


class Fashion(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="fashion")
    size = models.CharField(max_length=32, blank=True, default="")
    color = models.CharField(max_length=64, blank=True, default="")
    gender = models.CharField(max_length=32, blank=True, default="")
    brand = models.CharField(max_length=120, blank=True, default="")

    def __str__(self) -> str:
        return f"Fashion: {self.product.name}"
