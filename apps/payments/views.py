import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db import transaction
from .models import Payment
from .forms import TenantPaymentForm, LandlordConfirmForm

# WeasyPrint setup
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logging.warning("WeasyPrint not installed. PDF generation will be disabled.")

logger = logging.getLogger(__name__)

# ==================== EXISTING VIEWS (Preserved) ====================

@login_required
def my_payments(request):
    """Display payment history for the logged-in tenant."""
    payments = Payment.objects.filter(
        booking__tenant=request.user
    ).select_related('booking__property').order_by('-created_at')
    
    context = {
        'payments': payments,
        'pending_count': payments.filter(status='PENDING').count(),
        'completed_count': payments.filter(status='COMPLETED').count(),
    }
    return render(request, 'payments/my_payments.html', context)


@login_required
def landlord_payments(request):
    """Display all payments for properties owned by the logged-in landlord."""
    payments = Payment.objects.filter(
        booking__property__landlord=request.user
    ).select_related('booking', 'booking__tenant', 'booking__property').order_by('-created_at')
    
    context = {
        'payments': payments,
        'pending_count': payments.filter(status='TENANT_PAID').count(),
        'completed_count': payments.filter(status='COMPLETED').count(),
        'total_confirmed': sum(p.amount for p in payments if p.status == 'COMPLETED'),
    }
    return render(request, 'payments/landlord_payments.html', context)


@login_required
def verify_payment(request, payment_id):
    """
    Landlord-only view to verify and mark a tenant payment as completed.
    ✅ FIXED: Removed form dependency to prevent validation issues.
    """
    payment = get_object_or_404(Payment, id=payment_id)
    
    # Security: Only property landlord can verify
    if payment.booking.property.landlord != request.user:
        messages.error(request, "Permission denied. You can only verify payments for your own properties.")
        return redirect('core:dashboard')
    
    # Only allow verification if tenant has marked as paid
    if payment.status not in ['PENDING', 'TENANT_PAID']:
        messages.warning(request, 'This payment cannot be verified at this time.')
        return redirect('payments:landlord_payments')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # ✅ Get confirmation notes directly from POST (no form dependency)
                confirmation_notes = request.POST.get('confirmation_notes', '').strip()
                
                # Update Payment Status
                payment.status = 'COMPLETED'
                payment.paid_date = timezone.now().date()
                payment.landlord_confirmed_at = timezone.now()
                
                # Add landlord notes if provided
                if confirmation_notes:
                    if payment.payment_notes:
                        payment.payment_notes = f"{payment.payment_notes}\n[Landlord: {confirmation_notes}]"
                    else:
                        payment.payment_notes = f"[Landlord: {confirmation_notes}]"
                
                payment.save()
                
                # Update Booking Status to PAID
                booking = payment.booking
                if booking.status == 'CONFIRMED':
                    booking.status = 'PAID'
                    booking.save()
                
                messages.success(request, f"✅ Payment of TZS {payment.amount:,.0f} verified successfully!")
                return redirect('payments:landlord_payments')
                
        except Exception as e:
            logger.error(f"Error verifying payment {payment_id}: {e}")
            messages.error(request, f"Error verifying payment: {str(e)}")
            return redirect('payments:verify', payment_id=payment.id)
    
    # If GET request, show the verification form
    context = {
        'payment': payment,
    }
    return render(request, 'payments/verify_payment.html', context)



@login_required
def download_payment_slip(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id, booking__tenant=request.user)
    
    if not WEASYPRINT_AVAILABLE:
        return HttpResponse('PDF generation service is currently unavailable.', status=503)
    
    try:
        html_string = render_to_string('payments/payment_slip.html', {
            'payment': payment,
            'now': timezone.now(),
            'user': request.user
        })
        
        pdf_content = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="payment_slip_{payment.id}.pdf"'
        return response
    except Exception as e:
        logger.error(f"PDF generation failed for payment slip {payment_id}: {e}")
        return HttpResponse('Error generating payment slip.', status=500)


@login_required
def download_payment_invoice(request, payment_id):
    """Generate invoice PDF for a pending payment."""
    payment = get_object_or_404(Payment, id=payment_id, booking__tenant=request.user)
    
    if not WEASYPRINT_AVAILABLE:
        return HttpResponse('PDF generation service is currently unavailable.', status=503)
    
    try:
        html_string = render_to_string('payments/payment_invoice.html', {
            'payment': payment, 'user': request.user, 'now': timezone.now()
        })
        pdf_content = HTML(string=html_string).write_pdf()
        
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{payment.id}.pdf"'
        return response
    except Exception as e:
        logger.error(f"PDF generation failed for invoice {payment_id}: {e}")
        return HttpResponse('Error generating invoice.', status=500)


@login_required
def download_approved_payments_list(request):
    """Generate PDF list of all approved/completed payments."""
    payments = Payment.objects.filter(
        booking__tenant=request.user,
        status='COMPLETED'
    ).select_related('booking', 'booking__property').order_by('-paid_date')
    
    total_paid = sum(p.amount for p in payments)
    
    if not WEASYPRINT_AVAILABLE:
        return HttpResponse('PDF generation service is currently unavailable.', status=503)
    
    try:
        html_string = render_to_string('payments/approved_payments_list.html', {
            'payments': payments,
            'user': request.user,
            'now': timezone.now(),
            'total_paid': total_paid
        })
        pdf_content = HTML(string=html_string).write_pdf()
        
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="receipts_{request.user.username}.pdf"'
        return response
    except Exception as e:
        logger.error(f"PDF generation failed for receipts list: {e}")
        return HttpResponse('Error generating receipts list.', status=500)


# ====================OFFLINE PAYMENT FLOW WITH CALCULATION====================

@login_required
def mark_payment_made(request, booking_id):
    """
    Tenant: Mark payment as made after paying offline.
    Calculates total amount: Monthly Rent * Number of Months Booked.
    """
    from apps.bookings.models import Booking
    
    # 1. Get the Booking
    booking = get_object_or_404(Booking, id=booking_id, tenant=request.user, status='CONFIRMED')
    
    # 2. Calculate Number of Months
    move_in = booking.move_in_date
    move_out = booking.move_out_date
    
    # Simple month difference calculation
    months_diff = (move_out.year - move_in.year) * 12 + (move_out.month - move_in.month)
    
    # Ensure at least 1 month if dates are close or same month
    if months_diff <= 0:
        months_diff = 1
        
    # 3. Get Monthly Rent
    monthly_rent = booking.property.monthly_rent
    
    # 4. Calculate Total Amount Required
    total_amount = monthly_rent * months_diff
    
    # 5. Create or Get Payment Record
    # ✅ FIXED: Removed 'landlord' key because Payment model doesn't have this field
    payment, created = Payment.objects.get_or_create(
        booking=booking,
        defaults={
            'tenant': request.user,
            'amount': total_amount, 
            'status': 'PENDING',
            'due_date': move_in,
        }
    )

    # If payment already exists and is paid/completed, redirect to details
    if payment.status in ['TENANT_PAID', 'COMPLETED']:
        messages.info(request, 'Payment already processed.')
        return redirect('payments:payment_detail', payment_id=payment.id)

    if request.method == 'POST':
        form = TenantPaymentForm(request.POST, request.FILES, instance=payment)
        if form.is_valid():
            with transaction.atomic():
                payment = form.save(commit=False)
                
                # ✅ Enforce the calculated amount to prevent tampering
                payment.amount = total_amount 
                
                payment.status = 'TENANT_PAID'
                payment.tenant_paid_at = timezone.now()
                
                # Save extra fields from form if they exist
                if hasattr(form, 'cleaned_data'):
                    payment.payment_method = form.cleaned_data.get('payment_method')
                    payment.payment_reference = form.cleaned_data.get('payment_reference')
                    payment.payment_notes = form.cleaned_data.get('payment_notes')
                
                # Handle file upload if present
                if 'payment_proof' in request.FILES:
                    payment.payment_proof = request.FILES['payment_proof']
                    
                payment.save()
                
                messages.success(request, f'✅ Payment of TZS {total_amount:,.0f} marked as made! Landlord will verify receipt.')
                return redirect('payments:payment_detail', payment_id=payment.id)
    else:
        # Pre-fill form with calculated amount so tenant sees what they owe
        form = TenantPaymentForm(instance=payment, initial={'amount': total_amount})

    context = {
        'form': form,
        'booking': booking,
        'payment': payment,
        'is_new': created,
        'months_booked': months_diff,
        'monthly_rent': monthly_rent,
        'total_amount': total_amount,
    }
    return render(request, 'payments/mark_payment.html', context)


@login_required
def payment_detail(request, payment_id):
    """View payment details (accessible by tenant or landlord)"""
    payment = get_object_or_404(Payment, id=payment_id)
    
    if payment.tenant != request.user and payment.booking.property.landlord != request.user:
        messages.error(request, 'Unauthorized access.')
        return redirect('core:dashboard')
    
    is_landlord = (payment.booking.property.landlord == request.user)
    
    context = {
        'payment': payment,
        'is_landlord': is_landlord,
        'WEASYPRINT_AVAILABLE': WEASYPRINT_AVAILABLE,
    }
    return render(request, 'payments/payment_detail.html', context)


@login_required
def cancel_payment(request, payment_id):
    """Tenant: Cancel a payment before landlord confirms"""
    payment = get_object_or_404(Payment, id=payment_id, booking__tenant=request.user)
    
    if payment.status == 'COMPLETED':
        messages.error(request, 'Cannot cancel a confirmed payment.')
        return redirect('payments:payment_detail', payment_id=payment.id)
    
    if request.method == 'POST':
        with transaction.atomic():
            payment.status = 'CANCELLED'
            payment.save()
            
            booking = payment.booking
            if booking.status == 'PAID':
                booking.status = 'CONFIRMED'
                booking.save()
            
            messages.success(request, 'Payment cancelled successfully.')
            return redirect('payments:my_payments')
    
    context = {'payment': payment}
    return render(request, 'payments/cancel_payment.html', context)