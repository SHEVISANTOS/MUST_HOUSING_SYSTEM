# apps/users/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'users'
urlpatterns = [
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('login/', auth_views.LoginView.as_view(
        template_name='users/login.html',
        next_page='core:dashboard'
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(
        next_page='users:login'
    ), name='logout'),
]