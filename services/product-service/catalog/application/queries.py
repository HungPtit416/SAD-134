from .repositories import CategoryRepository, ProductRepository


class CatalogQueries:
    def __init__(self, *, categories: CategoryRepository, products: ProductRepository) -> None:
        self._categories = categories
        self._products = products

    def list_categories(self):
        return self._categories.list()

    def list_products(self):
        return self._products.list()

