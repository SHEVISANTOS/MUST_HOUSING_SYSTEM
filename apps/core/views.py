import logging

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Sum, Count, Q
from django.contrib.auth import authenticate, login, logout
from django.template.loader import render_to_string
from datetime import timedelta
import django
from django.conf import settings

from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking
from apps.payments.models import Payment

logger = logging.getLogger(__name__)


# ==========================================
# 📊 DASHBOARD & PROFILE
# ==========================================

def dashboard(request):
    """
    Role-based dashboard for tenants and landlords. This is the root URL
    ('/') - an anonymous visitor lands here first, so it sends them to the
    public property listing instead of forcing a login just to browse.
    """
    if not request.user.is_authenticated:
        return redirect('properties:list')

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
    """User profile page with update functionality"""
    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', request.user.first_name)
        request.user.last_name = request.POST.get('last_name', request.user.last_name)
        request.user.email = request.POST.get('email', request.user.email)
        request.user.phone = request.POST.get('phone', request.user.phone)
        request.user.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('core:profile')
    
    return render(request, 'profile.html', {'user': request.user})


# ==========================================
# 🔐 ADMIN HELPER & DASHBOARD
# ==========================================

def _is_admin(user):
    """Helper: Check if user is superuser or has ADMIN role"""
    return user.is_superuser or getattr(user, 'role', None) == 'ADMIN'


@login_required
def admin_dashboard(request):
    """Admin-only dashboard with system stats, reports, and configuration"""
    if not _is_admin(request.user):
        messages.error(request, "Access denied. Administrator privileges required.")
        return redirect('core:dashboard')

    stats = {
        'total_users': User.objects.count(),
        'landlords': User.objects.filter(role='LANDLORD').count(),
        'tenants': User.objects.filter(role='TENANT').count(),
        'properties': Property.objects.count(),
        'bookings': Booking.objects.count(),
        'completed_payments': Payment.objects.filter(status='COMPLETED').count(),
        'total_revenue': Payment.objects.filter(status='COMPLETED').aggregate(Sum('amount'))['amount__sum'] or 0,
    }

    sys_config = {
        'django_version': django.get_version(),
        'debug_mode': 'ON' if settings.DEBUG else 'OFF',
        'db_engine': settings.DATABASES['default']['ENGINE'].split('.')[-1],
        'media_path': settings.MEDIA_ROOT,
        'static_path': settings.STATIC_ROOT,
        'allowed_hosts': ', '.join(settings.ALLOWED_HOSTS),
    }

    return render(request, 'core/admin_dashboard.html', {
        'stats': stats,
        'sys_config': sys_config,
    })


# ==========================================
# 📊 REPORTS SYSTEM
# ==========================================

def _cols(*label_width_pairs):
    """
    Build a report_pdf.html columns list with per-column width hints (percent
    of table width). xhtml2pdf's table layout doesn't honor table-layout or
    word-break, so without explicit widths a long value (e.g. an email
    address) overflows into the next column instead of wrapping - passing
    (label, width) pairs here is what actually keeps columns contained.
    """
    return [{'label': label, 'width': width} for label, width in label_width_pairs]


def _render_report_pdf(filename, report_title, sections, report_period=None):
    """
    Shared renderer for the admin PDF reports below - builds the same
    branded letterhead (logo, watermark, teal styling) used for payment
    slips/invoices and tenancy contracts elsewhere in the app. `sections` is
    a list of dicts, each optionally with a 'heading', a 'stats' list of
    (label, value) pairs rendered as a figure strip, and/or a 'columns' +
    'rows' data table - see templates/core/report_pdf.html.
    """
    from apps.payments.views import PDF_AVAILABLE, _get_logo_data_uri, _get_watermark_data_uri

    if not PDF_AVAILABLE:
        return HttpResponse('PDF generation service is currently unavailable.', status=503)

    from xhtml2pdf import pisa

    html_string = render_to_string('core/report_pdf.html', {
        'report_title': report_title,
        'report_period': report_period,
        'generated_at': timezone.now(),
        'sections': sections,
        'logo': _get_logo_data_uri(),
        'watermark': _get_watermark_data_uri(),
    })

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'

    pisa_status = pisa.CreatePDF(html_string, dest=response)
    if pisa_status.err:
        logger.error("PDF generation failed for report: %s", report_title)
        return HttpResponse('Error generating report.', status=500)

    return response


@login_required
def reports_page(request):
    """Admin reports dashboard page"""
    if not _is_admin(request.user):
        messages.error(request, "Access denied. Administrator privileges required.")
        return redirect('core:dashboard')

    return render(request, 'core/reports.html')


@login_required
def manage_users(request):
    """Admin-only user management page with search & filter"""
    if not _is_admin(request.user):
        messages.error(request, "Access denied. Administrator privileges required.")
        return redirect('core:dashboard')
    
    # Start with all users
    users = User.objects.all().order_by('-date_joined')
    
    # Filter by role if specified
    role_filter = request.GET.get('role')
    if role_filter:
        users = users.filter(role=role_filter)
    
    # Search functionality
    search_query = request.GET.get('q')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    # ✅ PRE-CALCULATE COUNTS (Django templates can't do .filter().count())
    tenant_count = User.objects.filter(role='TENANT').count()
    landlord_count = User.objects.filter(role='LANDLORD').count()
    admin_count = User.objects.filter(role='ADMIN').count()
    
    context = {
        'users': users,
        'total_users': User.objects.count(),
        'tenant_count': tenant_count,
        'landlord_count': landlord_count,
        'admin_count': admin_count,
        'role_filter': role_filter,
        'search_query': search_query,
    }
    
    return render(request, 'core/manage_users.html', context)


@login_required
def export_payments_report(request):
    """Generate a branded PDF report of all payments"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    payments = Payment.objects.select_related('booking__tenant', 'booking__property').order_by('-created_at')
    total_amount = payments.aggregate(Sum('amount'))['amount__sum'] or 0
    completed_count = payments.filter(status='COMPLETED').count()

    sections = [
        {
            'stats': [
                ('Total Payments', payments.count()),
                ('Completed', completed_count),
                ('Total Amount', f'TZS {total_amount:,.0f}'),
            ],
        },
        {
            'heading': 'All Payments',
            'columns': _cols(
                ('Payment ID', 12), ('Tenant', 16), ('Property', 26),
                ('Amount (TZS)', 16), ('Status', 14), ('Date', 16),
            ),
            'rows': [
                [
                    str(p.id)[:8],
                    p.booking.tenant.username,
                    p.booking.property.title,
                    f'{p.amount:,.0f}',
                    p.get_status_display(),
                    p.created_at.strftime('%d %b %Y'),
                ]
                for p in payments
            ],
        },
    ]
    return _render_report_pdf('payments_report', 'Payments Report', sections)


@login_required
def export_bookings_report(request):
    """Generate a branded PDF report of all bookings"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    bookings = Booking.objects.select_related('tenant', 'property').order_by('-created_at')

    sections = [
        {
            'stats': [
                ('Total Bookings', bookings.count()),
                ('Confirmed', bookings.filter(status='CONFIRMED').count()),
                ('Pending', bookings.filter(status='PENDING').count()),
            ],
        },
        {
            'heading': 'All Bookings',
            'columns': _cols(
                ('Booking ID', 14), ('Tenant', 16), ('Property', 28),
                ('Status', 14), ('Move-In', 14), ('Move-Out', 14),
            ),
            'rows': [
                [
                    f"BK/{b.id:04d}",
                    b.tenant.username,
                    b.property.title,
                    b.get_status_display(),
                    b.move_in_date,
                    b.move_out_date,
                ]
                for b in bookings
            ],
        },
    ]
    return _render_report_pdf('bookings_report', 'Bookings Report', sections)


@login_required
def export_users_report(request):
    """Generate a branded PDF report of all users"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    users = User.objects.all().order_by('date_joined')

    sections = [
        {
            'stats': [
                ('Total Users', User.objects.count()),
                ('Tenants', User.objects.filter(role='TENANT').count()),
                ('Landlords', User.objects.filter(role='LANDLORD').count()),
                ('Verified', User.objects.filter(is_verified=True).count()),
            ],
        },
        {
            'heading': 'All Users',
            'columns': _cols(
                ('Username', 14), ('Email', 26), ('Role', 10), ('Phone', 14),
                ('Verified', 10), ('Active', 10), ('Joined', 16),
            ),
            'rows': [
                [
                    user.username,
                    user.email,
                    user.get_role_display(),
                    user.phone or 'N/A',
                    'Yes' if user.is_verified else 'No',
                    'Yes' if user.is_active else 'No',
                    user.date_joined.strftime('%d %b %Y'),
                ]
                for user in users
            ],
        },
    ]
    return _render_report_pdf('users_report', 'Users Report', sections)


@login_required
def export_properties_report(request):
    """Generate a branded PDF report of all properties"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    properties = Property.objects.select_related('landlord').all().order_by('-created_at')
    avg_rent = Property.objects.aggregate(avg=Sum('monthly_rent') / Count('id'))['avg'] if Property.objects.exists() else 0

    sections = [
        {
            'stats': [
                ('Total Properties', Property.objects.count()),
                ('Available', Property.objects.filter(is_available=True).count()),
                ('Occupied', Property.objects.filter(is_available=False).count()),
                ('Average Rent', f'TZS {avg_rent:,.0f}'),
            ],
        },
        {
            'heading': 'All Properties',
            'columns': _cols(
                ('Title', 20), ('Landlord', 14), ('Type', 12), ('Location', 20),
                ('Rent (TZS)', 14), ('Available', 10), ('Listed', 10),
            ),
            'rows': [
                [
                    prop.title,
                    prop.landlord.username,
                    prop.get_property_type_display(),
                    prop.location,
                    f'{prop.monthly_rent:,.0f}',
                    'Yes' if prop.is_available else 'No',
                    prop.created_at.strftime('%d %b %Y'),
                ]
                for prop in properties
            ],
        },
    ]
    return _render_report_pdf('properties_report', 'Properties Report', sections)


@login_required
def export_financial_report(request):
    """Generate a branded, comprehensive PDF financial report"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    total_revenue = Payment.objects.filter(status='COMPLETED').aggregate(Sum('amount'))['amount__sum'] or 0
    pending_revenue = Payment.objects.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0

    by_type_rows = []
    for type_code, type_name in Property.PROPERTY_TYPES:
        type_payments = Payment.objects.filter(
            booking__property__property_type=type_code,
            status='COMPLETED'
        )
        total = type_payments.aggregate(Sum('amount'))['amount__sum'] or 0
        count = type_payments.count()
        if count:
            by_type_rows.append([type_name, f'{total:,.0f}', count])

    recent_payments = Payment.objects.select_related('booking__tenant', 'booking__property').order_by('-created_at')[:50]

    sections = [
        {
            'heading': 'Revenue Summary',
            'stats': [
                ('Completed Revenue', f'TZS {total_revenue:,.0f}'),
                ('Pending Revenue', f'TZS {pending_revenue:,.0f}'),
                ('Total Expected', f'TZS {total_revenue + pending_revenue:,.0f}'),
            ],
        },
        {
            'heading': 'Revenue by Property Type',
            'columns': _cols(('Property Type', 40), ('Total Revenue (TZS)', 40), ('Payments', 20)),
            'rows': by_type_rows,
        },
        {
            'heading': 'Recent Transactions (Last 50)',
            'columns': _cols(
                ('Payment ID', 12), ('Tenant', 14), ('Property', 22), ('Amount (TZS)', 14),
                ('Status', 14), ('Method', 12), ('Date', 12),
            ),
            'rows': [
                [
                    str(p.id)[:8],
                    p.booking.tenant.username,
                    p.booking.property.title,
                    f'{p.amount:,.0f}',
                    p.get_status_display(),
                    p.get_payment_method_display() if p.payment_method else 'N/A',
                    p.created_at.strftime('%d %b %Y'),
                ]
                for p in recent_payments
            ],
        },
    ]
    return _render_report_pdf('financial_report', 'Financial Report', sections)


@login_required
def export_activity_report(request):
    """Generate a branded PDF system activity report (last 30 days)"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    now = timezone.now()
    last_30_days = now - timedelta(days=30)

    revenue_30 = Payment.objects.filter(
        created_at__gte=last_30_days, status='COMPLETED'
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    landlords = User.objects.filter(role='LANDLORD').annotate(
        prop_count=Count('properties', distinct=True),
        total_revenue=Sum('properties__bookings__payments__amount', filter=Q(properties__bookings__payments__status='COMPLETED'))
    ).order_by('-total_revenue')[:5]

    sections = [
        {
            'heading': 'User Activity',
            'stats': [
                ('New Users', User.objects.filter(date_joined__gte=last_30_days).count()),
                ('Active Users', User.objects.filter(last_login__gte=last_30_days).count()),
            ],
        },
        {
            'heading': 'Property & Booking Activity',
            'stats': [
                ('New Listings', Property.objects.filter(created_at__gte=last_30_days).count()),
                ('New Bookings', Booking.objects.filter(created_at__gte=last_30_days).count()),
                ('Confirmed', Booking.objects.filter(created_at__gte=last_30_days, status='CONFIRMED').count()),
            ],
        },
        {
            'heading': 'Payment Activity',
            'stats': [
                ('New Payments', Payment.objects.filter(created_at__gte=last_30_days).count()),
                ('Completed', Payment.objects.filter(created_at__gte=last_30_days, status='COMPLETED').count()),
                ('Revenue (30d)', f'TZS {revenue_30:,.0f}'),
            ],
        },
        {
            'heading': 'Top Landlords by Revenue',
            'columns': _cols(('Landlord', 34), ('Properties', 26), ('Total Revenue (TZS)', 40)),
            'rows': [
                [landlord.username, landlord.prop_count, f'{landlord.total_revenue or 0:,.0f}']
                for landlord in landlords
            ],
        },
    ]
    return _render_report_pdf('activity_report', 'Activity Report', sections, report_period='Last 30 Days')


# ==========================================
# 🔀 AUTHENTICATION & REDIRECTS
# ==========================================

@login_required
def post_login_redirect(request):
    """Redirect users to their role-specific dashboard after successful app login"""
    if _is_admin(request.user):
        return redirect('core:admin_dashboard')
    return redirect('core:dashboard')


def admin_login_view(request):
    """
    Custom login view for Django admin that redirects based on user role.
    """
    if request.user.is_authenticated:
        if _is_admin(request.user):
            return redirect('core:admin_dashboard')
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            if _is_admin(user):
                return redirect('core:admin_dashboard')
            return redirect('core:dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'admin/login.html')


@login_required
def custom_logout(request):
    """Handle logout - accepts both GET and POST"""
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('properties:list')