from django.urls import path
from . import views
from . import tenancy_views

app_name = 'bookings'

urlpatterns = [
    path('create/<int:property_id>/', views.create_booking, name='create_booking'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('landlord-bookings/', views.landlord_bookings, name='landlord_bookings'),
    path('approve/<int:booking_id>/', views.approve_booking, name='approve_booking'),
    path('reject/<int:booking_id>/', views.reject_booking, name='reject_booking'),
    path('view/<int:booking_id>/', views.view_booking, name='view_booking'),

    # Tenancy renewal flow
    path('tenancy/<int:tenancy_id>/request-renewal/', views.request_renewal, name='request_renewal'),
    path('tenancy/<int:tenancy_id>/decline-renewal/', views.decline_renewal, name='decline_renewal'),
    path('tenancy/<int:tenancy_id>/approve-renewal/', views.approve_renewal, name='approve_renewal'),

    # Tenant: My Contract
    path('my-contract/', tenancy_views.my_contract, name='my_contract'),
    path('tenancy/<int:tenancy_id>/give-notice/', tenancy_views.give_notice, name='give_notice'),
    path('tenancy/<int:tenancy_id>/contract.pdf', tenancy_views.download_contract_pdf, name='download_contract_pdf'),

    # Landlord: Occupancy
    path('occupancy/', tenancy_views.landlord_occupancy, name='landlord_occupancy'),
    path('tenancy/<int:tenancy_id>/terminate/', tenancy_views.terminate_tenancy, name='terminate_tenancy'),

    # Scheduled task (Vercel Cron), not user-facing - see tenancy_views for the auth check
    path('tasks/update-tenancy-statuses/', tenancy_views.cron_update_tenancy_statuses, name='cron_update_tenancy_statuses'),
]