# apps/users/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'users'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),
    path('custom-logout/', views.logout_view, name='custom_logout'),

    # ✅ FIXED: Removed 'next_page' so Django uses LOGIN_REDIRECT_URL from settings.py
    path('login/', auth_views.LoginView.as_view(
        template_name='users/login.html'
    ), name='login'),
    
    path('logout/', auth_views.LogoutView.as_view(
        next_page='users:login'
    ), name='logout'),
]