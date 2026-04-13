from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets

from ..infrastructure.models import Customer
from .serializers import CustomerSerializer


@api_view(["GET"])
def ping(_request):
    return Response({"status": "ok"})


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

