from decimal import Decimal

from ..application.repositories import CategoryRepository, ProductRepository
from ..domain.entities import CategoryEntity, ProductEntity
from .models import Category, Product


class DjangoCategoryRepository(CategoryRepository):
    def list(self) -> list[CategoryEntity]:
        return [CategoryEntity(id=c.id, name=c.name, slug=c.slug) for c in Category.objects.all()]


class DjangoProductRepository(ProductRepository):
    def list(self) -> list[ProductEntity]:
        qs = Product.objects.select_related("category").all()
        out: list[ProductEntity] = []
        for p in qs:
            out.append(
                ProductEntity(
                    id=p.id,
                    sku=p.sku,
                    name=p.name,
                    description=p.description,
                    price=Decimal(str(p.price)),
                    currency=p.currency,
                    category_id=p.category_id,
                    is_active=p.is_active,
                )
            )
        return out

