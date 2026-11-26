from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskViewSet, PersonalTodoViewSet, StickyNoteViewSet, TaskTimeLogViewSet

router = DefaultRouter()
router.register(r'personal-todos', PersonalTodoViewSet, basename='personal-todo')
router.register(r'sticky-notes', StickyNoteViewSet, basename='sticky-note')
router.register(r'time-logs', TaskTimeLogViewSet, basename='time-log')
router.register(r'', TaskViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),
]
