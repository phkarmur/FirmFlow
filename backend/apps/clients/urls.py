from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClientViewSet, ClientGroupViewSet, ClientContactViewSet

router = DefaultRouter()
router.register(r'groups', ClientGroupViewSet, basename='client-group')
router.register(r'contacts', ClientContactViewSet, basename='client-contact')
router.register(r'', ClientViewSet, basename='client')

urlpatterns = [
    path('', include(router.urls)),
]
