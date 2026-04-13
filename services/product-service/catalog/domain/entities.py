from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CategoryEntity:
    id: int
    name: str
    slug: str


@dataclass(frozen=True)
class ProductEntity:
    id: int
    sku: str
    name: str
    description: str
    price: Decimal
    currency: str
    category_id: int | None
    is_active: bool

