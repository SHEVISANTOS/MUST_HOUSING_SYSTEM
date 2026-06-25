# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# ✅ IMPORT: Your custom views from apps.core
from apps.core import views as core_views

urlpatterns = [
     
    path('admin/login/', core_views.admin_login_view, name='admin_login'),
    
    # Standard admin URLs (must come AFTER custom login)
    path('admin/', admin.site.urls),
    
    # App URLs
    path('', include('apps.core.urls')),
    path('users/', include('apps.users.urls')),
    path('properties/', include('apps.properties.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('payments/', include('apps.payments.urls')),
]

# Serve media/static in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)