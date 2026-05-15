from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

# Customize admin site
admin.site.site_header = "MUST Housing Administration"
admin.site.site_title = "MUST Housing Admin"
admin.site.index_title = "Welcome to MUST Housing Management System"

def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    return redirect('users:login')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_redirect, name='home'),
    path('users/', include('apps.users.urls')),
    path('properties/', include('apps.properties.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('payments/', include('apps.payments.urls')),
    path('dashboard/', include('apps.core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
