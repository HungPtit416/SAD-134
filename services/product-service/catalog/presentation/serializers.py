from rest_framework import serializers

from ..infrastructure.models import Book, Category, Electronics, Fashion, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "tag"]


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ["author", "publisher", "isbn", "language"]


class ElectronicsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Electronics
        fields = ["brand", "color", "warranty_months"]


class FashionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fashion
        fields = ["size", "color", "gender", "brand"]


class ProductRateSerializer(serializers.Serializer):
    stars = serializers.IntegerField(min_value=1, max_value=5)


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=Category.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    book = serializers.SerializerMethodField()
    electronics = serializers.SerializerMethodField()
    fashion = serializers.SerializerMethodField()
    book_data = BookSerializer(required=False, allow_null=True, write_only=True)
    electronics_data = ElectronicsSerializer(required=False, allow_null=True, write_only=True)
    fashion_data = FashionSerializer(required=False, allow_null=True, write_only=True)
    my_rating = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "description",
            "image",
            "main_category",
            "price",
            "currency",
            "ratings",
            "no_of_ratings",
            "category",
            "category_id",
            "is_active",
            "created_at",
            "book",
            "electronics",
            "fashion",
            "book_data",
            "electronics_data",
            "fashion_data",
            "my_rating",
        ]
        read_only_fields = ["ratings", "no_of_ratings", "my_rating"]

    def get_my_rating(self, obj: Product):
        user_id = self.context.get("user_id")
        if not isinstance(user_id, int) or user_id <= 0:
            return None
        review = obj.product_ratings.filter(user_id=user_id).first()
        return review.stars if review else None

    def get_book(self, obj: Product):
        try:
            return BookSerializer(obj.book).data
        except Book.DoesNotExist:
            return None

    def get_electronics(self, obj: Product):
        try:
            return ElectronicsSerializer(obj.electronics).data
        except Electronics.DoesNotExist:
            return None

    def get_fashion(self, obj: Product):
        try:
            return FashionSerializer(obj.fashion).data
        except Fashion.DoesNotExist:
            return None

    def _upsert_subtype(self, product: Product, validated_data: dict) -> None:
        main = product.main_category
        book_data = validated_data.get("book_data")
        electronics_data = validated_data.get("electronics_data")
        fashion_data = validated_data.get("fashion_data")

        if main == Product.MAIN_CATEGORY_BOOK:
            if book_data:
                Book.objects.update_or_create(product=product, defaults=book_data)
            else:
                Book.objects.get_or_create(product=product)
        elif main == Product.MAIN_CATEGORY_ELECTRONICS:
            if electronics_data:
                Electronics.objects.update_or_create(product=product, defaults=electronics_data)
            else:
                Electronics.objects.get_or_create(product=product)
        elif main == Product.MAIN_CATEGORY_FASHION:
            if fashion_data:
                Fashion.objects.update_or_create(product=product, defaults=fashion_data)
            else:
                Fashion.objects.get_or_create(product=product)

    def create(self, validated_data):
        book_data = validated_data.pop("book_data", None)
        electronics_data = validated_data.pop("electronics_data", None)
        fashion_data = validated_data.pop("fashion_data", None)
        product = Product.objects.create(**validated_data)
        self._upsert_subtype(
            product,
            {
                "book_data": book_data,
                "electronics_data": electronics_data,
                "fashion_data": fashion_data,
            },
        )
        return product

    def update(self, instance, validated_data):
        book_data = validated_data.pop("book_data", None)
        electronics_data = validated_data.pop("electronics_data", None)
        fashion_data = validated_data.pop("fashion_data", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        self._upsert_subtype(
            instance,
            {
                "book_data": book_data,
                "electronics_data": electronics_data,
                "fashion_data": fashion_data,
            },
        )
        return instance

    def to_internal_value(self, data):
        """Accept legacy nested keys book/electronics/fashion on write."""
        mutable = dict(data)
        for src, dst in (
            ("book", "book_data"),
            ("electronics", "electronics_data"),
            ("fashion", "fashion_data"),
        ):
            if src in mutable and dst not in mutable:
                mutable[dst] = mutable[src]
        return super().to_internal_value(mutable)
