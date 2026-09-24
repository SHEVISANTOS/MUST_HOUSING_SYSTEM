from django.contrib.auth import views as auth_views
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import resolve, Resolver404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .forms import CustomUserCreationForm
# Import models for counting stats
from apps.properties.models import Property
from apps.bookings.models import Booking


class CustomLoginView(auth_views.LoginView):
    """
    Same as Django's LoginView (next= handling and its safety validation
    are both already built in via RedirectURLMixin) - this just adds a
    friendlier message when the visitor arrived here from "Sign in to
    book" on a specific property.
    """
    def form_valid(self, form):
        response = super().form_valid(form)
        redirect_to = self.get_redirect_url()  # '' if absent/unsafe - already validated by Django
        if redirect_to:
            try:
                match = resolve(redirect_to)
            except Resolver404:
                match = None
            if match and match.view_name == 'bookings:create_booking':
                prop = Property.objects.filter(pk=match.kwargs.get('property_id')).first()
                if prop:
                    messages.success(self.request, f"Welcome back — you can now book {prop.title}.")
        return response


def _safe_next(request):
    """The next= param from GET or POST, or '' if missing/unsafe (open-redirect guard)."""
    candidate = request.POST.get('next') or request.GET.get('next', '')
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return ''


def register(request):
    """
    Handle user registration and auto-login after successful signup.
    Carries a next= through the form so a visitor who came here from
    "Sign in to book" (via the login page's "Create an account" link)
    lands back on the booking flow afterwards - unless they registered as
    a LANDLORD and next= pointed at a booking, since landlords can't book;
    they go to their dashboard instead with a short explanation.
    """
    next_url = _safe_next(request)

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Auto-login after registration
            messages.success(request, f"Welcome, {user.username}! Your account has been created successfully.")

            if next_url:
                is_booking_next = False
                try:
                    is_booking_next = resolve(next_url).view_name == 'bookings:create_booking'
                except Resolver404:
                    pass
                if is_booking_next and user.role == 'LANDLORD':
                    messages.info(request, "You're registered as a landlord — head to your dashboard to list a property.")
                    return redirect('core:dashboard')
                return redirect(next_url)

            return redirect('core:dashboard')
    else:
        form = CustomUserCreationForm()

    return render(request, 'users/register.html', {'form': form, 'next': next_url})


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
    return redirect('properties:list')