from django.contrib import admin
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import include, path
from django.http import JsonResponse

from apps.freight import views as freight_views

admin.site.site_header = 'Steadfast Freight Calculator Administration'
admin.site.site_title = 'Steadfast Freight Calculator Administration'
admin.site.index_title = 'Steadfast Freight Calculator Administration'
from apps.authentication_gateway.views import CalculatorLoginView


def health_check(request):
    return JsonResponse({
        'status': 'ok',
        'service': 'calc',
        'version': settings.APP_VERSION,
    })


def readiness_check(request):
    checks = {
        'database': 'unavailable',
        'migrations': 'unknown',
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        checks['database'] = 'ok'

        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        checks['migrations'] = 'pending' if pending else 'ok'
    except Exception:
        return JsonResponse({
            'status': 'not_ready',
            'service': 'calc',
            'version': settings.APP_VERSION,
            'checks': checks,
        }, status=503)

    status = 'ready' if checks['migrations'] == 'ok' else 'not_ready'
    return JsonResponse({
        'status': status,
        'service': 'calc',
        'version': settings.APP_VERSION,
        'checks': checks,
    }, status=200 if status == 'ready' else 503)


urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('ready/', readiness_check, name='readiness_check'),
    path("accounts/", include("apps.authentication_gateway.urls")),
    path(
        'accounts/login/',
        CalculatorLoginView.as_view(),
        name='login',
    ),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('admin/', admin.site.urls),
    path('', freight_views.calculator_page, name='freight_calculator'),
    path('api-tools/', freight_views.api_tools_page, name='api_tools'),
    path('api/suburbs/', freight_views.suburb_autocomplete, name='suburb_autocomplete'),
    path('api/products/', freight_views.product_autocomplete, name='product_autocomplete'),
    path('api/calculate/', freight_views.calculate_freight, name='calculate_freight'),
    path('api/v1/quotes/', freight_views.calculate_freight, name='quote_api_v1'),
    path('api/v1/freight-accounts/', freight_views.freight_accounts, name='freight_accounts_api_v1'),
    path('estimates/', include('apps.saved_estimates.urls')),
    path('api/estimates/', include('apps.saved_estimates.api_urls')),
]

handler403 = "apps.authentication_gateway.views.permission_denied_view"


