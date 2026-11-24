# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.utils.translation import gettext_lazy as _

from apps.core.seo import SITEMAPS
from apps.properties import views as property_views

# ✅ IMPORT: Your custom views from apps.core
from apps.core import views as core_views
from apps.payments import views as payment_views
from apps.bookings import tenancy_views

from urllib.parse import urlsplit
_LEGAL_CONTEXT = {'site_host': urlsplit(settings.SITE_URL).netloc or 'vothousefinding.com'}

urlpatterns = [
    # ---- Language-neutral: same address in every language ----
    path('healthz', core_views.healthz, name='healthz'),
    path('i18n/setlang/', core_views.set_language, name='set_language'),  # the EN | SW switch
    path('robots.txt', core_views.robots_txt),
    path('sitemap.xml', sitemap_view, {'sitemaps': SITEMAPS}, name='django.contrib.sitemaps.views.sitemap'),
    # Short path keeps the QR code printed on payment PDFs small
    path('v/<str:token>/', payment_views.verify_document, name='verify_document'),

    path(f'{settings.ADMIN_URL}login/', core_views.admin_login_view, name='admin_login'),
    # Standard admin URLs (must come AFTER custom login)
    path(settings.ADMIN_URL, admin.site.urls),
]

# ---- Everything people read: English at /..., Kiswahili at /sw/... ----
# Separate addresses per language are what lets Google index and show the
# Swahili pages to Swahili searchers (hreflang links tie each pair together).
urlpatterns += i18n_patterns(
    path('verify/', tenancy_views.verify_by_code, name='verify_by_code'),
    path('privacy/', TemplateView.as_view(template_name='legal/privacy.html', extra_context=_LEGAL_CONTEXT), name='privacy'),
    path('terms/', TemplateView.as_view(template_name='legal/terms.html', extra_context=_LEGAL_CONTEXT), name='terms'),
    path(_('houses-for-rent/<slug:slug>/'), property_views.area_page, name='area'),

    path('', include('apps.core.urls')),
    path('users/', include('apps.users.urls')),
    path('properties/', include('apps.properties.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('payments/', include('apps.payments.urls')),
    path('messages/', include('apps.messaging.urls')),
    path('notifications/', include('apps.notifications.urls')),
    prefix_default_language=False,
)

# Serve media/static in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)