from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # 📊 Dashboard & Profile
    path('', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    
    # 🔐 Admin Dashboard & Core Reports
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # ✅ Reports Page
    path('reports/', views.reports_page, name='reports_page'),
    
    # Report Exports
    path('reports/payments/', views.export_payments_report, name='export_payments'),
    path('reports/bookings/', views.export_bookings_report, name='export_bookings'),
    
    # 📈 Comprehensive System Reports
    path('reports/users/', views.export_users_report, name='export_users'),
    path('reports/properties/', views.export_properties_report, name='export_properties'),
    path('reports/financial/', views.export_financial_report, name='export_financial'),
    path('reports/activity/', views.export_activity_report, name='export_activity'),
    
    # 👥 User Management 
    path('manage-users/', views.manage_users, name='manage_users'),
    
    # ✅ Login redirect handler
    path('login-redirect/', views.post_login_redirect, name='post_login_redirect'),
    
    # ✅ Logout (✅ NEW - for secure POST logout)
    path('logout/', views.custom_logout, name='logout'),
]