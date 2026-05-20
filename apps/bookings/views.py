import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Booking
from apps.properties.models import Property

logger = logging.getLogger(__name__)

# ==================== TENANT VIEWS ====================

@login_required
def create_booking(request, property_id):
    """
    Tenant view to submit a booking request for a specific property.
    Status starts as 'PENDING' awaiting landlord approval.
    """
    # Ensure user is a tenant
    if request.user.role != 'TENANT':
        messages.error(request, "Only tenants can book properties.")
        return redirect('properties:detail', pk=property_id)

    # Get property and ensure it's available
    prop = get_object_or_404(Property, id=property_id, is_available=True)

    if request.method == 'POST':
        move_in_date = request.POST.get('move_in_date')
        move_out_date = request.POST.get('move_out_date')

        # Basic Validation
        if not move_in_date or not move_out_date:
            messages.error(request, "Please provide both move-in and move-out dates.")
        elif move_in_date >= move_out_date:
            messages.error(request, "Move-out date must be after move-in date.")
        else:
            try:
                # Create booking with PENDING status
                booking = Booking.objects.create(
                    property=prop,
                    tenant=request.user,
                    move_in_date=move_in_date,
                    move_out_date=move_out_date,
                    status='PENDING'
                )
                
                messages.success(request, "✅ Booking request submitted! Awaiting landlord approval.")
                return redirect('bookings:my_bookings')
            
            except Exception as e:
                logger.error(f"Booking creation failed: {e}")
                messages.error(request, "An error occurred while creating the booking. Please try again.")

    context = {'property': prop}
    return render(request, 'bookings/create.html', context)


@login_required
def my_bookings(request):
    """
    Display all bookings for the logged-in tenant.
    """
    bookings = Booking.objects.filter(
        tenant=request.user
    ).select_related('property').order_by('-created_at')
    
    context = {
        'bookings': bookings,
        'pending_count': bookings.filter(status='PENDING').count(),
        'confirmed_count': bookings.filter(status='CONFIRMED').count(),
    }
    return render(request, 'bookings/my_bookings.html', context)


# ==================== LANDLORD VIEWS ====================

@login_required
def landlord_bookings(request):
    """
    Display all bookings for properties owned by the logged-in landlord.
    Allows filtering by status (Pending, Confirmed, etc.).
    """
    bookings = Booking.objects.filter(
        property__landlord=request.user
    ).select_related('property', 'tenant').order_by('-created_at')
    
    context = {
        'bookings': bookings,
        'pending_count': bookings.filter(status='PENDING').count(),
        'confirmed_count': bookings.filter(status='CONFIRMED').count(),
        'paid_count': bookings.filter(status='PAID').count(),
    }
    return render(request, 'bookings/landlord_bookings.html', context)


@login_required
def approve_booking(request, booking_id):
    """
    Landlord approves a pending booking.
    - Changes status to 'CONFIRMED'.
    - Automatically creates a 'PENDING' payment record for the tenant.
    """
    if request.user.role != 'LANDLORD':
        messages.error(request, "Unauthorized access.")
        return redirect('core:dashboard')

    booking = get_object_or_404(Booking, id=booking_id, property__landlord=request.user)

    if booking.status != 'PENDING':
        messages.warning(request, "This booking cannot be approved in its current state.")
        return redirect('bookings:landlord_bookings')

    try:
        # 1. Update Booking Status
        booking.status = 'CONFIRMED'
        booking.save()

        # 2. Auto-create Payment Record (Offline Workflow)
        from apps.payments.models import Payment
        
        # Use get_or_create to prevent duplicates if clicked twice
        Payment.objects.get_or_create(
            booking=booking,
            defaults={
                'tenant': booking.tenant,
                'landlord': booking.property.landlord,
                'amount': booking.property.monthly_rent, # Or use a calculated total if needed
                'due_date': booking.move_in_date,
                'status': 'PENDING', # Tenant needs to mark this as paid
            }
        )

        messages.success(request, "✅ Booking approved successfully! Payment invoice generated for tenant.")
        
    except Exception as e:
        logger.error(f"Error approving booking {booking_id}: {e}")
        messages.error(request, "An error occurred while approving the booking.")

    return redirect('bookings:landlord_bookings')


@login_required
def reject_booking(request, booking_id):
    """
    Landlord rejects a pending booking.
    - Changes status to 'CANCELLED'.
    """
    if request.user.role != 'LANDLORD':
        messages.error(request, "Unauthorized access.")
        return redirect('core:dashboard')

    booking = get_object_or_404(Booking, id=booking_id, property__landlord=request.user)

    if booking.status != 'PENDING':
        messages.warning(request, "This booking cannot be rejected in its current state.")
        return redirect('bookings:landlord_bookings')

    try:
        booking.status = 'CANCELLED'
        booking.save()
        messages.error(request, "❌ Booking rejected.")
    except Exception as e:
        logger.error(f"Error rejecting booking {booking_id}: {e}")
        messages.error(request, "An error occurred while rejecting the booking.")

    return redirect('bookings:landlord_bookings')


# ==================== SHARED / UTILITY VIEWS ====================

@login_required
def view_booking(request, booking_id):
    """
    Shared view for both Tenants and Landlords to see details of a specific booking.
    Displays relevant actions based on role and status.
    """
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Security Check
    is_landlord = (request.user.role == 'LANDLORD' and booking.property.landlord == request.user)
    is_tenant = (request.user.role == 'TENANT' and booking.tenant == request.user)
    
    if not is_landlord and not is_tenant:
        messages.error(request, "Unauthorized access to this booking.")
        return redirect('core:dashboard')

    context = {
        'booking': booking,
        'is_landlord': is_landlord,
        'is_tenant': is_tenant,
    }
    return render(request, 'bookings/view_booking.html', context)