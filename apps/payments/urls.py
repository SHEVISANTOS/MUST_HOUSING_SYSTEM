"""
Payment Module URL Configuration
--------------------------------
NOTE: Payment model uses UUID primary keys, so all payment_id params use <uuid:...>
Booking model uses integer IDs, so booking_id params use <int:...>
"""

from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # ==================== TENANT URLs ====================
    
    # Payment records & documents (UUID params)
    path('my-payments/', views.my_payments, name='my_payments'),
    path('slip/<uuid:payment_id>/download/', views.download_payment_slip, name='download_slip'),
    path('invoice/<uuid:payment_id>/download/', views.download_payment_invoice, name='download_invoice'),
    
    # Payment workflow actions (booking_id stays int, payment_id is uuid)
    path('booking/<int:booking_id>/pay/', views.mark_payment_made, name='mark_payment'),
    path('payment/<uuid:payment_id>/', views.payment_detail, name='payment_detail'),
    path('payment/<uuid:payment_id>/cancel/', views.cancel_payment, name='cancel_payment'),
    
    # ==================== LANDLORD URLs ====================
    
    # Payment management & verification (UUID params)
    path('landlord/payments/', views.landlord_payments, name='landlord_payments'),
    
    # Verification routes (both map to same view for flexibility)
    path('verify/<uuid:payment_id>/', views.verify_payment, name='verify'),
    path('landlord/payment/<uuid:payment_id>/confirm/', views.verify_payment, name='confirm_payment'),
    path('verify/<uuid:payment_id>/', views.verify_payment, name='verify'),
]