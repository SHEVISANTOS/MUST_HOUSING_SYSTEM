import calendar
import logging
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.formats import date_format
from .models import Booking, Tenancy
from apps.properties.models import Property

logger = logging.getLogger(__name__)


def _tenancy_conflicting_with(property_id, move_in_date_str):
    """
    The live Tenancy (upcoming/active/ending_soon) whose date range contains
    the requested move-in date, if any - used to give the tenant early,
    friendly feedback on the booking form itself. Returns None if the date
    string is malformed too, since the existing basic-validation branch
    ahead of this one already covers that case for the user-facing message.
    """
    move_in_date = parse_date(move_in_date_str)
    if move_in_date is None:
        return None
    return Tenancy.objects.filter(
        property_id=property_id,
        status__in=['upcoming', 'active', 'ending_soon'],
        start_date__lte=move_in_date,
        end_date__gte=move_in_date,
    ).order_by('start_date').first()


def _months_between(start_date, end_date):
    """Whole calendar months between two dates, minimum 1."""
    months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    return max(1, months)


def _add_months(date_obj, months):
    """Add whole calendar months to a date, clamping the day for short months."""
    month_index = date_obj.month - 1 + months
    year = date_obj.year + month_index // 12
    month = month_index % 12 + 1
    day = min(date_obj.day, calendar.monthrange(year, month)[1])
    return date_obj.replace(year=year, month=month, day=day)


def _check_no_overlap(property_id, start_date, end_date, exclude_booking_id=None):
    """
    Raises ValidationError if another CONFIRMED/PAID booking or another live
    Tenancy for this property overlaps [start_date, end_date]. Callers must
    hold a row lock on the Property (select_for_update) before calling this,
    otherwise two concurrent approvals could both pass the check.
    """
    booking_overlap = Booking.objects.filter(
        property_id=property_id,
        status__in=['CONFIRMED', 'PAID'],
        move_in_date__lte=end_date,
        move_out_date__gte=start_date,
    )
    if exclude_booking_id:
        booking_overlap = booking_overlap.exclude(id=exclude_booking_id)
    if booking_overlap.exists():
        raise ValidationError("Another confirmed booking already overlaps these dates for this property.")

    tenancy_overlap = Tenancy.objects.filter(
        property_id=property_id,
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).exclude(status__in=['terminated', 'renewed'])
    if tenancy_overlap.exists():
        raise ValidationError("Another active tenancy already overlaps these dates for this property.")


def _create_tenancy(booking, property_obj, duration_months):
    """
    Creates the Tenancy for a just-approved/renewed booking. Assumes the
    caller already ran _check_no_overlap() while holding the property's row
    lock; full_clean() here is a defensive re-check (also validates the
    OneToOne uniqueness on `booking`), not the primary race-condition guard.
    """
    today = timezone.localdate()
    tenancy = Tenancy(
        booking=booking,
        property=property_obj,
        tenant=booking.tenant,
        start_date=booking.move_in_date,
        end_date=booking.move_out_date,
        duration_months=duration_months,
        status='active' if booking.move_in_date <= today else 'upcoming',
    )
    tenancy.full_clean()
    tenancy.save()
    return tenancy

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
        elif (conflict := _tenancy_conflicting_with(prop.id, move_in_date)) is not None:
            # Early, friendly feedback - the real, race-safe overlap guard
            # is still enforced at approval time in approve_booking().
            messages.error(
                request,
                f"This property is occupied until {date_format(conflict.end_date, 'j M Y')} "
                f"— earliest move-in {date_format(conflict.available_from, 'j M Y')}."
            )
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
    - Rejects if another confirmed booking or active tenancy overlaps the dates.
    - Changes status to 'CONFIRMED'.
    - Automatically creates a 'PENDING' payment record for the tenant.
    - Creates the Tenancy that tracks the occupancy period.
    """
    if request.user.role != 'LANDLORD':
        messages.error(request, "Unauthorized access.")
        return redirect('core:dashboard')

    booking = get_object_or_404(Booking, id=booking_id, property__landlord=request.user)

    if booking.status != 'PENDING':
        messages.warning(request, "This booking cannot be approved in its current state.")
        return redirect('bookings:landlord_bookings')

    from apps.payments.models import Payment

    try:
        with transaction.atomic():
            # Lock the property row so two concurrent approvals for
            # overlapping dates can't both pass the overlap check below.
            property_obj = Property.objects.select_for_update().get(pk=booking.property_id)

            move_in = booking.move_in_date
            move_out = booking.move_out_date
            months_diff = _months_between(move_in, move_out)

            _check_no_overlap(property_obj.id, move_in, move_out, exclude_booking_id=booking.id)

            booking.status = 'CONFIRMED'
            booking.save()

            # Auto-create Payment Record (Offline Workflow)
            total_amount = property_obj.monthly_rent * months_diff
            Payment.objects.get_or_create(
                booking=booking,
                defaults={
                    'tenant': booking.tenant,
                    'amount': total_amount,
                    'due_date': booking.move_in_date,
                    'status': 'PENDING', # Tenant needs to mark this as paid
                }
            )

            _create_tenancy(booking, property_obj, months_diff)

        messages.success(request, "✅ Booking approved successfully! Payment invoice generated for tenant.")

    except ValidationError as e:
        messages.error(request, f"Cannot approve: {' '.join(e.messages)}")
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


# ==================== TENANCY / RENEWAL VIEWS ====================
# Note: redirects below point at the existing my_bookings/landlord_bookings
# pages as placeholders. They'll switch to the dedicated my_contract /
# landlord_occupancy pages once those are built (views/templates step).

@login_required
def request_renewal(request, tenancy_id):
    """Tenant requests to renew their tenancy; landlord must approve it."""
    tenancy = get_object_or_404(Tenancy, id=tenancy_id, tenant=request.user)

    if tenancy.display_status not in ('active', 'ending_soon'):
        messages.warning(request, "Renewal can only be requested for an active tenancy.")
    elif tenancy.renewal_requested:
        messages.info(request, "You've already requested a renewal for this tenancy.")
    else:
        tenancy.renewal_requested = True
        tenancy.save(update_fields=['renewal_requested', 'updated_at'])
        messages.success(request, "✅ Renewal request sent to your landlord.")

    return redirect('bookings:my_contract')


@login_required
def decline_renewal(request, tenancy_id):
    """Landlord declines a tenant's renewal request. The tenancy is untouched."""
    if request.user.role != 'LANDLORD':
        messages.error(request, "Unauthorized access.")
        return redirect('core:dashboard')

    tenancy = get_object_or_404(Tenancy, id=tenancy_id, property__landlord=request.user)
    tenancy.renewal_requested = False
    tenancy.save(update_fields=['renewal_requested', 'updated_at'])
    messages.info(request, "Renewal request declined.")

    return redirect('bookings:landlord_occupancy')


@login_required
def approve_renewal(request, tenancy_id):
    """
    Landlord approves a renewal request:
    - Creates a new, auto-confirmed Booking starting the day after the
      current tenancy ends, for the same duration.
    - Creates its Payment (same amount calculation as a normal approval).
    - Creates the new Tenancy.
    - Marks the old Tenancy 'renewed'.
    """
    if request.user.role != 'LANDLORD':
        messages.error(request, "Unauthorized access.")
        return redirect('core:dashboard')

    old_tenancy = get_object_or_404(Tenancy, id=tenancy_id, property__landlord=request.user)

    if not old_tenancy.renewal_requested:
        messages.warning(request, "No renewal has been requested for this tenancy.")
        return redirect('bookings:landlord_occupancy')

    from apps.payments.models import Payment

    try:
        with transaction.atomic():
            # Lock the property row - same reasoning as approve_booking.
            property_obj = Property.objects.select_for_update().get(pk=old_tenancy.property_id)

            new_start = old_tenancy.end_date + timezone.timedelta(days=1)
            new_end = _add_months(new_start, old_tenancy.duration_months)

            _check_no_overlap(property_obj.id, new_start, new_end)

            new_booking = Booking.objects.create(
                property=property_obj,
                tenant=old_tenancy.tenant,
                move_in_date=new_start,
                move_out_date=new_end,
                status='CONFIRMED',
            )

            total_amount = property_obj.monthly_rent * old_tenancy.duration_months
            Payment.objects.create(
                booking=new_booking,
                tenant=old_tenancy.tenant,
                amount=total_amount,
                due_date=new_start,
                status='PENDING',
            )

            _create_tenancy(new_booking, property_obj, old_tenancy.duration_months)

            old_tenancy.status = 'renewed'
            old_tenancy.renewal_requested = False
            old_tenancy.save(update_fields=['status', 'renewal_requested', 'updated_at'])

        messages.success(request, f"✅ Renewal approved. New contract runs {new_start} to {new_end}.")

    except ValidationError as e:
        messages.error(request, f"Cannot renew: {' '.join(e.messages)}")
    except Exception as e:
        logger.error(f"Error approving renewal for tenancy {tenancy_id}: {e}")
        messages.error(request, "An error occurred while approving the renewal.")

    return redirect('bookings:landlord_occupancy')