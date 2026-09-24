# apps/properties/views.py
from datetime import datetime

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Prefetch, Q, Exists, OuterRef
from .models import Property, PropertyImage
from .forms import PropertyForm

# Statuses that represent a live, occupying tenancy (as opposed to the two
# terminal states - terminated/renewed - which no longer block a property).
_LIVE_TENANCY_STATUSES = ['upcoming', 'active', 'ending_soon']


@login_required
def property_list(request):
    """
    Display list of available properties with search/filter.

    Seeker privacy: this view and properties/list.html only ever deal with
    Tenancy.start_date/end_date/status - never .tenant - so seekers cannot
    see who is renting a property, only that it's occupied and until when.
    """
    from apps.bookings.models import Tenancy  # local import: avoids a
    # module-level circular import (apps.bookings.models imports Property).

    # ✅ Prefetch images and each property's live tenancies to prevent N+1
    # queries when every card computes its own occupancy badge.
    relevant_tenancies = Tenancy.objects.filter(
        status__in=_LIVE_TENANCY_STATUSES
    ).order_by('start_date')

    queryset = Property.objects.filter(is_available=True).prefetch_related(
        'images',
        Prefetch('tenancies', queryset=relevant_tenancies, to_attr='prefetched_tenancies'),
    )

    search_query = request.GET.get('q')
    max_price = request.GET.get('max_price')
    property_type = request.GET.get('type')
    location = request.GET.get('location')
    available_now = request.GET.get('available_now')
    available_by = request.GET.get('available_by')  # YYYY-MM-DD

    if search_query:
        queryset = queryset.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query))
    if max_price:
        queryset = queryset.filter(monthly_rent__lte=max_price)
    if property_type:
        queryset = queryset.filter(property_type=property_type)
    if location:
        queryset = queryset.filter(location__icontains=location)

    # Both filters are DB-level (not just the Python-side prefetch check
    # above), since filtering needs to be correct before any pagination -
    # a property is a match if NO live tenancy covers the target date.
    if available_now:
        from django.utils import timezone
        today = timezone.localdate()
        occupied_today = Tenancy.objects.filter(
            property=OuterRef('pk'), status__in=_LIVE_TENANCY_STATUSES,
            start_date__lte=today, end_date__gte=today,
        )
        queryset = queryset.annotate(_occupied=Exists(occupied_today)).filter(_occupied=False)
    elif available_by:
        try:
            target_date = datetime.strptime(available_by, '%Y-%m-%d').date()
            occupied_on_date = Tenancy.objects.filter(
                property=OuterRef('pk'), status__in=_LIVE_TENANCY_STATUSES,
                start_date__lte=target_date, end_date__gte=target_date,
            )
            queryset = queryset.annotate(_occupied=Exists(occupied_on_date)).filter(_occupied=False)
        except ValueError:
            pass  # malformed date in the query string - ignore the filter rather than error out

    return render(request, 'properties/list.html', {
        'properties': queryset,
        'property_types': Property.PROPERTY_TYPES,
        'available_now': available_now,
        'available_by': available_by,
    })

@login_required
def property_detail(request, pk):
    """
    Display property details with images & map.

    Seeker privacy: `current_tenancy` and `timeline_tenancies` are only ever
    used in the template for their dates/status - see the note in
    _availability_timeline.html about never adding tenant fields there.
    """
    from apps.bookings.models import Tenancy  # local import, see property_list
    from django.utils import timezone
    import datetime as dt

    prop = get_object_or_404(Property.objects.prefetch_related('images'), pk=pk)

    today = timezone.localdate()
    window_days = 365
    window_end = today + dt.timedelta(days=window_days)
    live_tenancies = list(
        prop.tenancies.filter(
            status__in=_LIVE_TENANCY_STATUSES,
            start_date__lte=window_end,
            end_date__gte=today,
        ).order_by('start_date')
    )
    current_tenancy = next(
        (t for t in live_tenancies if t.start_date <= today <= t.end_date), None
    )

    # Plain dicts, not Tenancy objects: the timeline only ever needs dates
    # and a display flag, and building it this way makes it structurally
    # impossible for the template to reach a tenant's name/phone/etc, even
    # by accident - there's simply no .tenant on a dict.
    timeline_blocks = []
    for t in live_tenancies:
        block_start = max(t.start_date, today)
        block_end = min(t.end_date, window_end)
        offset_days = (block_start - today).days
        span_days = (block_end - block_start).days + 1
        timeline_blocks.append({
            'left_pct': round(offset_days / window_days * 100, 2),
            'width_pct': round(span_days / window_days * 100, 2),
            'start_date': t.start_date,
            'end_date': t.end_date,
            'is_ending_soon': t.display_status == 'ending_soon',
        })

    return render(request, 'properties/detail.html', {
        'property': prop,
        'current_tenancy': current_tenancy,
        'timeline_blocks': timeline_blocks,
        'timeline_start': today,
        'timeline_end': window_end,
    })

@login_required
def property_create(request):
    """Landlord view to create new property listing with images & map"""
    if request.user.role != 'LANDLORD':
        messages.error(request, "Only landlords can list properties.")
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        form = PropertyForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # 1️⃣ Save property (without committing to DB yet)
                prop = form.save(commit=False)
                prop.landlord = request.user
                prop.is_available = True 
                prop.save()
                
                # 2️⃣ Handle multiple image uploads
                images = request.FILES.getlist('property_images')
                if images:
                    for i, image in enumerate(images):
                        PropertyImage.objects.create(
                            property=prop,
                            image=image,
                            is_primary=(i == 0)  # First uploaded image = primary
                        )
                
                messages.success(request, f"✅ Property '{prop.title}' listed successfully with {len(images)} image(s)!")
                return redirect('properties:detail', pk=prop.id)
                
            except Exception as e:
                messages.error(request, f"Error creating property: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PropertyForm()
    
    return render(request, 'properties/create.html', {'form': form})

@login_required
def my_properties(request):
    """Landlord-only view to see their own properties"""
    if request.user.role != 'LANDLORD':
        messages.error(request, "Access denied.")
        return redirect('core:dashboard')
    
    # ✅ Prefetch images for faster rendering
    properties = Property.objects.filter(landlord=request.user).prefetch_related('images').order_by('-created_at')
    return render(request, 'properties/my_properties.html', {
        'properties': properties,
        'total': properties.count(),
        'available': properties.filter(is_available=True).count()
    })