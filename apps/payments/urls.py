from django.urls import path
from . import views

app_name = 'payments'
urlpatterns = [
    # Tenant URLs
    path('my-payments/', views.my_payments, name='my_payments'),
    path('slip/<int:payment_id>/download/', views.download_payment_slip, name='download_slip'),
    
    # Landlord URLs
    path('landlord/payments/', views.landlord_payments, name='landlord_payments'),
    path('verify/<int:payment_id>/', views.verify_payment, name='verify'),
]