from abc import ABC, abstractmethod

from ..domain.entities import CategoryEntity, ProductEntity


class CategoryRepository(ABC):
    @abstractmethod
    def list(self) -> list[CategoryEntity]:
        raise NotImplementedError


class ProductRepository(ABC):
    @abstractmethod
    def list(self) -> list[ProductEntity]:
        raise NotImplementedError

