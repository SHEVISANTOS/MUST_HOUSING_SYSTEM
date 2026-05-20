from django.urls import path
from . import views

app_name = 'bookings'

urlpatterns = [
    path('create/<int:property_id>/', views.create_booking, name='create_booking'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('landlord-bookings/', views.landlord_bookings, name='landlord_bookings'),
    path('approve/<int:booking_id>/', views.approve_booking, name='approve_booking'),
    path('reject/<int:booking_id>/', views.reject_booking, name='reject_booking'),
    path('view/<int:booking_id>/', views.view_booking, name='view_booking'),
]