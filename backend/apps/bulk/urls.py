from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BulkBatchViewSet

router = DefaultRouter()
router.register(r'batches', BulkBatchViewSet, basename='bulk-batch')

urlpatterns = [
    path('', include(router.urls)),
]
