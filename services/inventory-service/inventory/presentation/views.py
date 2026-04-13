from rest_framework import viewsets

from ..infrastructure.models import StockItem
from .serializers import StockItemSerializer


class StockItemViewSet(viewsets.ModelViewSet):
    queryset = StockItem.objects.all()
    serializer_class = StockItemSerializer

