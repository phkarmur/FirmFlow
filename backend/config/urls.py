from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from django.http import HttpResponse
from apps.common.views import HealthCheckView, RootApiView

urlpatterns = [
    path('', RootApiView.as_view(), name='root'),
    path('favicon.ico', lambda r: HttpResponse(status=204)),
    path('admin/', admin.site.urls),
    path('healthz', HealthCheckView.as_view(), name='healthz'),
    path('healthz/', HealthCheckView.as_view(), name='healthz_slash'),

    # OpenAPI Schema & Docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API Version 1
    path('api/v1/auth/', include('apps.accounts.urls_auth')),
    path('api/v1/accounts/', include('apps.accounts.urls')),
    path('api/v1/clients/', include('apps.clients.urls')),
    path('api/v1/services/', include('apps.services.urls')),
    path('api/v1/periods/', include('apps.periods.urls')),
    path('api/v1/tasks/', include('apps.tasks.urls')),
    path('api/v1/bulk/', include('apps.bulk.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/reports/', include('apps.reports.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
