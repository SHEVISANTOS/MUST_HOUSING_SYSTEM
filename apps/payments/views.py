import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.template.loader import render_to_string

from .models import Payment

# WeasyPrint setup
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logging.warning("WeasyPrint not installed. PDF generation will be disabled.")

logger = logging.getLogger(__name__)


@login_required
def my_payments(request):
    """Display payment history for the logged-in tenant."""
    payments = Payment.objects.filter(booking__tenant=request.user).order_by('-due_date')
    return render(request, 'payments/my_payments.html', {'payments': payments})


@login_required
def landlord_payments(request):
    """Display all payments for properties owned by the logged-in landlord."""
    payments = Payment.objects.filter(
        booking__property__landlord=request.user
    ).select_related('booking', 'booking__tenant', 'booking__property').order_by('-due_date')
    
    return render(request, 'payments/landlord_payments.html', {'payments': payments})


@login_required
def verify_payment(request, payment_id):
    """Landlord-only view to verify and mark a tenant payment as completed."""
    payment = get_object_or_404(Payment, id=payment_id)
    
    if payment.booking.property.landlord != request.user:
        messages.error(request, "Permission denied. You can only verify payments for your own properties.")
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        payment.status = 'COMPLETED'
        payment.paid_date = timezone.now().date()
        payment.save()
        
        messages.success(request, f"Payment of TZS {payment.amount:,.0f} verified successfully!")
        return redirect('payments:landlord_payments')
    
    return render(request, 'payments/verify_payment.html', {'payment': payment})


@login_required
def download_payment_slip(request, payment_id):
    """Generate and download a payment instruction slip as PDF."""
    payment = get_object_or_404(Payment, id=payment_id, booking__tenant=request.user)
    if not WEASYPRINT_AVAILABLE:
        return HttpResponse('PDF generation service is currently unavailable.', status=503)
    
    try:
        html_string = render_to_string('payments/payment_slip.html', {
            'payment': payment, 'user': request.user, 'now': timezone.now()
        })
        pdf_content = HTML(string=html_string).write_pdf()
        
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="payment_slip_{payment.id}.pdf"'
        return response
    except Exception as e:
        logger.error(f"PDF generation failed for payment {payment_id}: {e}")
        messages.error(request, "Failed to generate PDF. Please try again later.")
        return redirect('payments:my_payments')


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
    
    # Calculate total paid amount in Python (Django templates don't have a built-in sum filter)
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