from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FinancialYearViewSet, PeriodViewSet

router = DefaultRouter()
router.register(r'financial-years', FinancialYearViewSet, basename='financial-year')
router.register(r'periods', PeriodViewSet, basename='period')

urlpatterns = [
    path('', include(router.urls)),
]
