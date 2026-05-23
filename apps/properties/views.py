# apps/properties/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import Property, PropertyImage
from .forms import PropertyForm

@login_required
def property_list(request):
    """Display list of available properties with search/filter"""
    # ✅ Prefetch images to prevent N+1 database queries
    queryset = Property.objects.filter(is_available=True).prefetch_related('images')
    
    search_query = request.GET.get('q')
    max_price = request.GET.get('max_price')
    property_type = request.GET.get('type')
    location = request.GET.get('location')
    
    if search_query:
        queryset = queryset.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query))
    if max_price:
        queryset = queryset.filter(monthly_rent__lte=max_price)
    if property_type:
        queryset = queryset.filter(property_type=property_type)
    if location:
        queryset = queryset.filter(location__icontains=location)
        
    return render(request, 'properties/list.html', {'properties': queryset})

@login_required
def property_detail(request, pk):
    """Display property details with images & map"""
    # ✅ Prefetch images for efficient loading
    prop = get_object_or_404(Property.objects.prefetch_related('images'), pk=pk)
    return render(request, 'properties/detail.html', {'property': prop})

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