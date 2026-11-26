from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ServiceCategoryViewSet, ServiceViewSet, TaskTypeViewSet,
    TaskTypeTodoTemplateViewSet, MilestoneViewSet, PendingIssueLabelViewSet, ComplianceEventViewSet
)

router = DefaultRouter()
router.register(r'categories', ServiceCategoryViewSet, basename='service-category')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'task-types', TaskTypeViewSet, basename='task-type')
router.register(r'todo-templates', TaskTypeTodoTemplateViewSet, basename='todo-template')
router.register(r'milestones', MilestoneViewSet, basename='milestone')
router.register(r'issue-labels', PendingIssueLabelViewSet, basename='issue-label')
router.register(r'compliance-calendar', ComplianceEventViewSet, basename='compliance-calendar')

urlpatterns = [
    path('', include(router.urls)),
]
