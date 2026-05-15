# apps/properties/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import Property
from .forms import PropertyForm

@login_required
def property_list(request):
    """Display list of available properties with search/filter"""
    queryset = Property.objects.filter(is_available=True)
    
    # Search filters
    search_query = request.GET.get('q')
    max_price = request.GET.get('max_price')
    property_type = request.GET.get('type')
    location = request.GET.get('location')
    
    if search_query:
        queryset = queryset.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
    
    if max_price:
        queryset = queryset.filter(monthly_rent__lte=max_price)
    
    if property_type:
        queryset = queryset.filter(property_type=property_type)
    
    if location:
        queryset = queryset.filter(location__icontains=location)
    
    context = {
        'properties': queryset,
    }
    return render(request, 'properties/list.html', context)

@login_required
def property_detail(request, pk):
    """Display property details"""
    property = get_object_or_404(Property, pk=pk)
    return render(request, 'properties/detail.html', {'property': property})

@login_required
def property_create(request):
    """Landlord view to create new property listing"""
    if request.user.role != 'LANDLORD':
        messages.error(request, "Only landlords can list properties.")
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        form = PropertyForm(request.POST)
        if form.is_valid():
            prop = form.save(commit=False)
            prop.landlord = request.user  # Auto-assign landlord
            prop.save()
            messages.success(request, "Property listed successfully!")
            return redirect('properties:list')
    else:
        form = PropertyForm()
    
    return render(request, 'properties/create.html', {'form': form})