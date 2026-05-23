from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .forms import CustomUserCreationForm
# Import models for counting stats
from apps.properties.models import Property
from apps.bookings.models import Booking


def register(request):
    """Handle user registration and auto-login after successful signup."""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Auto-login after registration
            messages.success(request, f"Welcome, {user.username}! Your account has been created successfully.")
            return redirect('core:dashboard')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'users/register.html', {'form': form})


@login_required
def profile(request):
    """
    Display user profile information and statistics.
    Calculates total properties (for landlords) and total bookings.
    """
    user = request.user
    
    # Initialize counts
    total_properties = 0
    total_bookings_received = 0
    
    if user.role == 'LANDLORD':
        # Count properties owned by this landlord
        # Note: Ensure Property model has related_name='properties' on the landlord ForeignKey
        total_properties = Property.objects.filter(landlord=user).count()
        
        # ✅ FIX: Count all bookings for properties owned by this landlord
        total_bookings_received = Booking.objects.filter(property__landlord=user).count()
        
    elif user.role == 'TENANT':
        # Count bookings made by this tenant
        total_bookings_received = Booking.objects.filter(tenant=user).count()

    context = {
        'user': user,
        'total_properties': total_properties,
        'total_bookings_received': total_bookings_received,
    }
    
    # Adjust template path if your profile template is located elsewhere
    return render(request, 'users/profile.html', context)


def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('users:login')