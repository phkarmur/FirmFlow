from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, BranchViewSet, FirmSettingsView, FirmLogoView

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'branches', BranchViewSet, basename='branch')

urlpatterns = [
    path('firm/', FirmSettingsView.as_view(), name='firm_settings'),
    path('firm/logo/', FirmLogoView.as_view(), name='firm_logo'),
    path('', include(router.urls)),
]
