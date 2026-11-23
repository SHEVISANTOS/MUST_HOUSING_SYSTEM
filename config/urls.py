# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

# ✅ IMPORT: Your custom views from apps.core
from apps.core import views as core_views
from apps.payments import views as payment_views
from apps.bookings import tenancy_views

from urllib.parse import urlsplit
_LEGAL_CONTEXT = {'site_host': urlsplit(settings.SITE_URL).netloc or 'vothousefinding.com'}

urlpatterns = [

    path('healthz', core_views.healthz, name='healthz'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    # Short path keeps the QR code printed on payment PDFs small
    path('v/<str:token>/', payment_views.verify_document, name='verify_document'),
    path('verify/', tenancy_views.verify_by_code, name='verify_by_code'),
    path('privacy/', TemplateView.as_view(template_name='legal/privacy.html', extra_context=_LEGAL_CONTEXT), name='privacy'),
    path('terms/', TemplateView.as_view(template_name='legal/terms.html', extra_context=_LEGAL_CONTEXT), name='terms'),

    path(f'{settings.ADMIN_URL}login/', core_views.admin_login_view, name='admin_login'),

    # Standard admin URLs (must come AFTER custom login)
    path(settings.ADMIN_URL, admin.site.urls),
    
    # App URLs
    path('', include('apps.core.urls')),
    path('users/', include('apps.users.urls')),
    path('properties/', include('apps.properties.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('payments/', include('apps.payments.urls')),
    path('messages/', include('apps.messaging.urls')),
    path('notifications/', include('apps.notifications.urls')),
]

# Serve media/static in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)