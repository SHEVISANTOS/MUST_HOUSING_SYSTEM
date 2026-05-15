from django.urls import path
from . import views

app_name = 'bookings'
urlpatterns = [
    path('create/<int:property_id>/', views.create_booking, name='create'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('landlord-bookings/', views.landlord_bookings, name='landlord_bookings'),
    path('approve/<int:booking_id>/', views.landlord_approve_booking, name='approve'),
]