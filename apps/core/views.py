from django.shortcuts import render, redirect  
from django.contrib.auth.decorators import login_required
from django.contrib import messages 
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Sum, Count, Q
from django.contrib.auth import authenticate, login, logout
from datetime import timedelta
import csv
import django
from django.conf import settings

from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking
from apps.payments.models import Payment


# ==========================================
# 📊 DASHBOARD & PROFILE
# ==========================================

@login_required
def dashboard(request):
    """Role-based dashboard for tenants and landlords"""
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
    """Generate CSV report of all payments"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payments_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Payment ID', 'Tenant', 'Property', 'Amount (TZS)', 'Status', 'Date'])

    for p in Payment.objects.select_related('booking__tenant', 'booking__property'):
        writer.writerow([
            str(p.id)[:8],
            p.booking.tenant.username,
            p.booking.property.title,
            p.amount,
            p.status,
            p.created_at.strftime('%Y-%m-%d')
        ])
    return response


@login_required
def export_bookings_report(request):
    """Generate CSV report of all bookings"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bookings_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Booking ID', 'Tenant', 'Property', 'Status', 'Move-In', 'Move-Out'])

    for b in Booking.objects.select_related('tenant', 'property'):
        writer.writerow([
            f"BK/{b.id:04d}",
            b.tenant.username,
            b.property.title,
            b.status,
            b.move_in_date,
            b.move_out_date
        ])
    return response


@login_required
def export_users_report(request):
    """Generate CSV report of all users"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="users_report.csv"'
    writer = csv.writer(response)
    
    writer.writerow(['MUST HOUSING SYSTEM - USERS REPORT'])
    writer.writerow(['Generated:', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])
    writer.writerow(['Username', 'Email', 'Role', 'Phone', 'Is Verified', 'Is Active', 'Date Joined', 'Last Login'])
    
    for user in User.objects.all().order_by('date_joined'):
        writer.writerow([
            user.username,
            user.email,
            user.role,
            user.phone or 'N/A',
            'Yes' if user.is_verified else 'No',
            'Yes' if user.is_active else 'No',
            user.date_joined.strftime('%Y-%m-%d'),
            user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never'
        ])
    
    writer.writerow([])
    writer.writerow(['SUMMARY'])
    writer.writerow(['Total Users:', User.objects.count()])
    writer.writerow(['Tenants:', User.objects.filter(role='TENANT').count()])
    writer.writerow(['Landlords:', User.objects.filter(role='LANDLORD').count()])
    writer.writerow(['Admins:', User.objects.filter(role='ADMIN').count()])
    writer.writerow(['Verified Users:', User.objects.filter(is_verified=True).count()])
    
    return response


@login_required
def export_properties_report(request):
    """Generate CSV report of all properties"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="properties_report.csv"'
    writer = csv.writer(response)
    
    writer.writerow(['MUST HOUSING SYSTEM - PROPERTIES REPORT'])
    writer.writerow(['Generated:', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])
    writer.writerow(['Property ID', 'Title', 'Landlord', 'Type', 'Location', 'Monthly Rent (TZS)', 
                     'Distance (km)', 'Amenities', 'Is Available', 'Created Date'])
    
    for prop in Property.objects.select_related('landlord').all().order_by('-created_at'):
        writer.writerow([
            prop.id,
            prop.title,
            prop.landlord.username,
            prop.get_property_type_display(),
            prop.location,
            prop.monthly_rent,
            prop.distance_from_must_km,
            prop.amenities or 'None',
            'Yes' if prop.is_available else 'No',
            prop.created_at.strftime('%Y-%m-%d')
        ])
    
    writer.writerow([])
    writer.writerow(['SUMMARY'])
    writer.writerow(['Total Properties:', Property.objects.count()])
    writer.writerow(['Available Properties:', Property.objects.filter(is_available=True).count()])
    writer.writerow(['Occupied Properties:', Property.objects.filter(is_available=False).count()])
    avg_rent = Property.objects.aggregate(avg=Sum('monthly_rent')/Count('id'))['avg'] if Property.objects.exists() else 0
    writer.writerow(['Average Rent:', f"TZS {avg_rent:,.0f}"])
    
    return response


@login_required
def export_financial_report(request):
    """Generate comprehensive financial report"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="financial_report.csv"'
    writer = csv.writer(response)
    
    writer.writerow(['MUST HOUSING SYSTEM - FINANCIAL REPORT'])
    writer.writerow(['Generated:', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])
    
    total_revenue = Payment.objects.filter(status='COMPLETED').aggregate(Sum('amount'))['amount__sum'] or 0
    pending_revenue = Payment.objects.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0
    
    writer.writerow(['REVENUE SUMMARY'])
    writer.writerow(['Total Completed Revenue:', f'TZS {total_revenue:,.0f}'])
    writer.writerow(['Pending Revenue:', f'TZS {pending_revenue:,.0f}'])
    writer.writerow(['Total Expected Revenue:', f'TZS {total_revenue + pending_revenue:,.0f}'])
    writer.writerow([])
    
    writer.writerow(['REVENUE BY PROPERTY TYPE'])
    writer.writerow(['Property Type', 'Total Revenue (TZS)', 'Number of Payments'])
    
    for prop_type in Property.PROPERTY_TYPES:
        type_code, type_name = prop_type
        payments = Payment.objects.filter(
            booking__property__property_type=type_code,
            status='COMPLETED'
        )
        total = payments.aggregate(Sum('amount'))['amount__sum'] or 0
        count = payments.count()
        writer.writerow([type_name, f'TZS {total:,.0f}', count])
    
    writer.writerow([])
    writer.writerow(['RECENT TRANSACTIONS (Last 50)'])
    writer.writerow(['Payment ID', 'Tenant', 'Property', 'Amount (TZS)', 'Status', 'Payment Method', 'Date'])
    
    recent_payments = Payment.objects.select_related('booking__tenant', 'booking__property').order_by('-created_at')[:50]
    for p in recent_payments:
        writer.writerow([
            str(p.id)[:8],
            p.booking.tenant.username,
            p.booking.property.title,
            p.amount,
            p.status,
            p.payment_method or 'N/A',
            p.created_at.strftime('%Y-%m-%d')
        ])
    
    return response


@login_required
def export_activity_report(request):
    """Generate system activity report (Last 30 Days)"""
    if not _is_admin(request.user):
        return HttpResponse("Unauthorized", status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="activity_report.csv"'
    writer = csv.writer(response)
    
    writer.writerow(['MUST HOUSING SYSTEM - ACTIVITY REPORT'])
    writer.writerow(['Generated:', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Report Period:', 'Last 30 Days'])
    writer.writerow([])
    
    now = timezone.now()
    last_30_days = now - timedelta(days=30)
    
    writer.writerow(['USER ACTIVITY'])
    writer.writerow(['New Users:', User.objects.filter(date_joined__gte=last_30_days).count()])
    writer.writerow(['Active Users (logged in):', User.objects.filter(last_login__gte=last_30_days).count()])
    writer.writerow([])
    
    writer.writerow(['PROPERTY ACTIVITY'])
    writer.writerow(['New Properties Listed:', Property.objects.filter(created_at__gte=last_30_days).count()])
    writer.writerow(['Properties Updated:', Property.objects.filter(updated_at__gte=last_30_days).count()])
    writer.writerow([])
    
    writer.writerow(['BOOKING ACTIVITY'])
    writer.writerow(['New Bookings:', Booking.objects.filter(created_at__gte=last_30_days).count()])
    writer.writerow(['Confirmed:', Booking.objects.filter(created_at__gte=last_30_days, status='CONFIRMED').count()])
    writer.writerow(['Completed:', Booking.objects.filter(created_at__gte=last_30_days, status='PAID').count()])
    writer.writerow([])
    
    writer.writerow(['PAYMENT ACTIVITY'])
    writer.writerow(['New Payments:', Payment.objects.filter(created_at__gte=last_30_days).count()])
    writer.writerow(['Completed Payments:', Payment.objects.filter(created_at__gte=last_30_days, status='COMPLETED').count()])
    
    revenue_30 = Payment.objects.filter(created_at__gte=last_30_days, status='COMPLETED').aggregate(Sum('amount'))['amount__sum'] or 0
    writer.writerow(['Revenue (Last 30 Days):', f'TZS {revenue_30:,.0f}'])
    writer.writerow([])
    
    writer.writerow(['TOP LANDLORDS (By Revenue)'])
    writer.writerow(['Landlord', 'Properties', 'Total Revenue (TZS)'])
    
    landlords = User.objects.filter(role='LANDLORD').annotate(
        prop_count=Count('properties'),
        total_revenue=Sum('properties__booking__payment__amount', filter=Q(properties__booking__payment__status='COMPLETED'))
    ).order_by('-total_revenue')[:5]
    
    for landlord in landlords:
        writer.writerow([
            landlord.username,
            landlord.prop_count,
            f'TZS {landlord.total_revenue or 0:,.0f}'
        ])
    
    return response


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
    return redirect('users:login')