from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Booking
from apps.properties.models import Property

@login_required
def create_booking(request, property_id):
    """Tenant view to book a property"""
    prop = get_object_or_404(Property, id=property_id, is_available=True)
    
    # Only tenants can book
    if request.user.role != 'TENANT':
        messages.error(request, "Only tenants can book properties.")
        return redirect('properties:detail', pk=property_id)

    if request.method == 'POST':
        move_in = request.POST.get('move_in_date')
        move_out = request.POST.get('move_out_date')
        
        if not move_in or not move_out:
            messages.error(request, "Please provide both move-in and move-out dates.")
        elif move_in >= move_out:
            messages.error(request, "Move-out date must be after move-in date.")
        else:
            # Create booking with PENDING status
            booking = Booking.objects.create(
                property=prop,
                tenant=request.user,
                move_in_date=move_in,
                move_out_date=move_out,
                status='PENDING'  # ✅ Starts as PENDING
            )
            
            messages.success(request, "Booking request submitted! Awaiting landlord approval.")
            return redirect('bookings:my_bookings')  # ✅ Redirect to tenant's bookings
    
    return render(request, 'bookings/create.html', {'property': prop})


@login_required
def my_bookings(request):
    """Display tenant's booking history"""
    bookings = Booking.objects.filter(
        tenant=request.user
    ).select_related('property').order_by('-created_at')
    
    return render(request, 'bookings/my_bookings.html', {'bookings': bookings})


@login_required
def landlord_bookings(request):
    """Display landlord's booking management"""
    bookings = Booking.objects.filter(
        property__landlord=request.user
    ).select_related('property', 'tenant').order_by('-created_at')
    
    return render(request, 'bookings/landlord_bookings.html', {'bookings': bookings})


@login_required
def landlord_approve_booking(request, booking_id):
    """Landlord approves or rejects a booking"""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Security: Only property landlord can approve
    if booking.property.landlord != request.user:
        messages.error(request, "Permission denied.")
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            booking.status = 'CONFIRMED'
            booking.save()
            
            # ✅ Auto-create payment ONLY after approval
            from apps.payments.models import Payment
            Payment.objects.get_or_create(
                booking=booking,
                defaults={
                    'amount': booking.property.monthly_rent,
                    'due_date': booking.move_in_date,
                    'status': 'PENDING'
                }
            )
            messages.success(request, "Booking approved. Payment invoice generated for tenant.")
            
        elif action == 'reject':
            booking.status = 'CANCELLED'
            booking.save()
            messages.warning(request, "Booking rejected.")
            
        return redirect('bookings:landlord_bookings')
        
    return render(request, 'bookings/approve.html', {'booking': booking})