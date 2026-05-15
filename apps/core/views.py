from django.shortcuts import render, redirect  
from django.contrib.auth.decorators import login_required
from django.contrib import messages 
from django.utils import timezone

from apps.properties.models import Property
from apps.bookings.models import Booking
from apps.payments.models import Payment

@login_required
def dashboard(request):
    context = {
        'user': request.user,
        'today': timezone.now(),
    }
    
    if request.user.role == 'TENANT':
        context['total_properties'] = Property.objects.filter(is_available=True).count()
        context['active_bookings'] = Booking.objects.filter(
            tenant=request.user, status='CONFIRMED'
        ).count()
        context['total_bookings'] = Booking.objects.filter(tenant=request.user).count()
        context['recent_bookings'] = Booking.objects.filter(
            tenant=request.user
        ).select_related('property').order_by('-created_at')[:5]
        context['upcoming_payments'] = Payment.objects.filter(
            booking__tenant=request.user, status='PENDING'
        ).order_by('due_date')[:5]
        
    else:  # LANDLORD
        context['my_properties'] = Property.objects.filter(landlord=request.user)
        context['total_bookings'] = Booking.objects.filter(
            property__landlord=request.user
        ).count()
        context['pending_bookings'] = Booking.objects.filter(
            property__landlord=request.user, status='PENDING'
        ).count()
        context['recent_bookings'] = Booking.objects.filter(
            property__landlord=request.user
        ).select_related('property', 'tenant').order_by('-created_at')[:5]
        context['upcoming_payments'] = Payment.objects.filter(
            booking__property__landlord=request.user, status='PENDING'
        ).order_by('due_date')[:5]
    
    return render(request, 'dashboard.html', context)

@login_required
def profile(request):
    """User profile page"""
    if request.method == 'POST':
        # Update profile information
        request.user.first_name = request.POST.get('first_name', request.user.first_name)
        request.user.last_name = request.POST.get('last_name', request.user.last_name)
        request.user.email = request.POST.get('email', request.user.email)
        request.user.phone = request.POST.get('phone', request.user.phone)
        request.user.save()
        
        messages.success(request, 'Profile updated successfully!')  # ✅ Now works
        return redirect('core:profile')  # ✅ Now works
    
    return render(request, 'profile.html', {'user': request.user})