# apps/properties/views.py
from datetime import datetime

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Prefetch, Q, Exists, OuterRef
from django.views.decorators.http import require_POST
from .models import Property, PropertyImage, SavedProperty
from .forms import PropertyForm

# Statuses that represent a live, occupying tenancy (as opposed to the two
# terminal states - terminated/renewed - which no longer block a property).
_LIVE_TENANCY_STATUSES = ['upcoming', 'active', 'ending_soon']


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
    sort = request.GET.get('sort', 'recommended')

    if search_query:
        queryset = queryset.filter(
            Q(title__icontains=search_query) | Q(description__icontains=search_query) | Q(location__icontains=search_query)
        )
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

    sort_options = {
        'recommended': '-created_at',
        'price_low': 'monthly_rent',
        'nearest': 'distance_from_center_km',
        'newest': '-created_at',
    }
    queryset = queryset.order_by(sort_options.get(sort, sort_options['recommended']), 'id')

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Preserve every filter param except `page` when building pagination
    # links, so going to page 2 doesn't silently drop the active search.
    querystring = request.GET.copy()
    querystring.pop('page', None)

    # Quick-filter chips are plain links, not form submit buttons, each
    # carrying the FULL current querystring with just their own param
    # toggled - a <button type=submit> sharing a form with other chip
    # buttons would drop every other chip's state on click, since only the
    # clicked button's name/value is included in a form submission.
    def _chip_url(**overrides):
        qs = request.GET.copy()
        qs.pop('page', None)
        for key, value in overrides.items():
            if value is None:
                qs.pop(key, None)
            else:
                qs[key] = value
        return f"{request.path}?{qs.urlencode()}"

    available_now_url = _chip_url(available_now=None if available_now else '1')
    budget_chips = [
        (label, _chip_url(max_price=str(value)), max_price == str(value))
        for label, value in [('Under 100k', 100000), ('Under 200k', 200000), ('Under 500k', 500000)]
    ]

    return render(request, 'properties/list.html', {
        'properties': page_obj,
        'page_obj': page_obj,
        'querystring': querystring.urlencode(),
        'property_types': Property.PROPERTY_TYPES,
        'available_now': available_now,
        'available_now_url': available_now_url,
        'available_by': available_by,
        'sort': sort,
        'search_query': search_query or '',
        'max_price': max_price or '',
        'property_type': property_type or '',
        'location': location or '',
        'budget_chips': budget_chips,
    })

def property_detail(request, pk):
    """
    Display property details with images & map. Public - no login required
    (see apps.bookings.views.create_booking for where sign-in is enforced).

    Seeker privacy: `current_tenancy` and `timeline_tenancies` are only ever
    used in the template for their dates/status - see the note in
    _availability_timeline.html about never adding tenant fields there.
    """
    from apps.bookings.models import Tenancy  # local import, see property_list
    from django.templatetags.static import static
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

    # og:image deliberately always uses the site logo, never a property
    # photo: this deployment has no cloud storage configured (no
    # django-storages/S3/Cloudinary), MEDIA_ROOT is local disk, and nothing
    # serves /media/ in production (Django's own media serving is wrapped
    # in `if settings.DEBUG`, and vercel.json has no /media/ route). A
    # property-photo og:image would work when previewed locally and break
    # silently in production - the logo is the one image guaranteed to be
    # reachable (served via whitenoise from /static/).
    og_image_url = request.build_absolute_uri(static('img/vot_logo.png'))
    og_url = request.build_absolute_uri(request.path)

    relevant_tenancies = Tenancy.objects.filter(status__in=_LIVE_TENANCY_STATUSES).order_by('start_date')
    similar_properties = Property.objects.filter(
        property_type=prop.property_type, is_available=True,
    ).exclude(pk=prop.pk).prefetch_related(
        'images',
        Prefetch('tenancies', queryset=relevant_tenancies, to_attr='prefetched_tenancies'),
    )[:4]

    return render(request, 'properties/detail.html', {
        'property': prop,
        'current_tenancy': current_tenancy,
        'timeline_blocks': timeline_blocks,
        'timeline_start': today,
        'timeline_end': window_end,
        'og_image_url': og_image_url,
        'og_url': og_url,
        'similar_properties': similar_properties,
    })

@login_required
def property_create(request):
    """Landlord view to create new property listing with images & map"""
    if request.user.role != 'LANDLORD':
        messages.error(request, "Only landlords can list properties.")
        return redirect('core:dashboard')
    
    MAX_IMAGES = 10
    MAX_IMAGE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB

    if request.method == 'POST':
        form = PropertyForm(request.POST, request.FILES)
        if form.is_valid():
            images = request.FILES.getlist('property_images')
            oversized = [img.name for img in images if img.size > MAX_IMAGE_SIZE_BYTES]
            if len(images) > MAX_IMAGES:
                messages.error(request, f"You can upload up to {MAX_IMAGES} images only ({len(images)} selected).")
            elif oversized:
                messages.error(request, f"Each image must be 2MB or smaller. Too large: {', '.join(oversized)}")
            else:
                try:
                    # 1️⃣ Save property (without committing to DB yet)
                    prop = form.save(commit=False)
                    prop.landlord = request.user
                    prop.is_available = True
                    prop.status = 'live'
                    prop.save()

                    # 2️⃣ Handle multiple image uploads
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

@login_required
def property_edit(request, pk):
    """Landlord view to edit one of their own property listings."""
    prop = get_object_or_404(Property, pk=pk)
    if prop.landlord_id != request.user.id:
        messages.error(request, "You can only edit your own properties.")
        return redirect('properties:my_properties')

    MAX_IMAGES = 10
    MAX_IMAGE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB

    if request.method == 'POST':
        form = PropertyForm(request.POST, request.FILES, instance=prop)
        if form.is_valid():
            images = request.FILES.getlist('property_images')
            oversized = [img.name for img in images if img.size > MAX_IMAGE_SIZE_BYTES]
            if len(images) > MAX_IMAGES:
                messages.error(request, f"You can upload up to {MAX_IMAGES} images at once ({len(images)} selected).")
            elif oversized:
                messages.error(request, f"Each image must be 2MB or smaller. Too large: {', '.join(oversized)}")
            else:
                form.save()
                has_primary = prop.images.filter(is_primary=True).exists()
                for i, image in enumerate(images):
                    PropertyImage.objects.create(
                        property=prop,
                        image=image,
                        is_primary=(i == 0 and not has_primary),
                    )
                messages.success(request, f"✅ '{prop.title}' updated successfully.")
                return redirect('properties:detail', pk=prop.id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PropertyForm(instance=prop)

    return render(request, 'properties/edit.html', {'form': form, 'property': prop})

@require_POST
@login_required
def property_pause(request, pk):
    """Landlord quick action: pause a live listing, or reactivate a paused one."""
    prop = get_object_or_404(Property, pk=pk)
    if prop.landlord_id != request.user.id:
        messages.error(request, "You can only manage your own properties.")
        return redirect('properties:my_properties')

    if prop.status == 'paused':
        prop.status = 'live'
        prop.is_available = True
        messages.success(request, f"'{prop.title}' is live again.")
    else:
        prop.status = 'paused'
        prop.is_available = False
        messages.success(request, f"'{prop.title}' is paused and hidden from search.")
    prop.save(update_fields=['status', 'is_available', 'updated_at'])

    return redirect('properties:my_properties')


@require_POST
@login_required
def toggle_saved(request, pk):
    """
    Heart-button toggle. Called via fetch() from the listing card/detail
    page, so it returns JSON rather than redirecting - falls back to a
    plain redirect only if JS is unavailable (form submits normally).
    """
    prop = get_object_or_404(Property, pk=pk)
    saved, created = SavedProperty.objects.get_or_create(user=request.user, property=prop)
    if not created:
        saved.delete()
        is_saved = False
    else:
        is_saved = True

    if request.headers.get('x-requested-with') == 'fetch':
        return JsonResponse({'saved': is_saved})

    messages.success(request, f"{'Saved' if is_saved else 'Removed from saved'}: {prop.title}")
    return redirect(request.POST.get('next') or 'properties:detail', pk=pk)


@login_required
def saved_properties(request):
    """A seeker's bookmarked listings."""
    from apps.bookings.models import Tenancy

    relevant_tenancies = Tenancy.objects.filter(status__in=_LIVE_TENANCY_STATUSES).order_by('start_date')
    properties = Property.objects.filter(saved_by__user=request.user).prefetch_related(
        'images',
        Prefetch('tenancies', queryset=relevant_tenancies, to_attr='prefetched_tenancies'),
    ).order_by('-saved_by__created_at')

    return render(request, 'properties/saved.html', {'properties': properties})