# apps/properties/forms.py

from django import forms
from .models import Property, PropertyImage

class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = [
            'title', 'description', 'property_type', 'location',
            'distance_from_center_km', 'monthly_rent', 'amenities',
            'min_months', 'max_months', 'months_per_payment',
            'latitude', 'longitude', 'google_maps_link', 'is_available'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Spacious 2BR near city center'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe your property...'}),
            'property_type': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Ilemela, Mwanza'}),
            'distance_from_center_km': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'monthly_rent': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 150000'}),
            'amenities': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'water, electricity, wifi, parking'}),
            'min_months': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 3', 'min': 1}),
            'max_months': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 12', 'min': 1}),
            'months_per_payment': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': 'e.g., -8.9094'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': 'e.g., 33.4607'}),
            'google_maps_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://maps.app.goo.gl/...'}),
            'is_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class PropertyBasicsForm(forms.ModelForm):
    """Step 1 of the property wizard - what the place is."""
    class Meta:
        model = Property
        fields = ['title', 'description', 'property_type', 'location']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Spacious 2BR near city center'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe your property...'}),
            'property_type': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Ilemela, Mwanza'}),
        }


class PropertyLocationForm(forms.ModelForm):
    """Step 3 of the property wizard - where it is."""
    class Meta:
        model = Property
        fields = ['distance_from_center_km', 'latitude', 'longitude', 'google_maps_link']
        widgets = {
            'distance_from_center_km': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'placeholder': 'e.g., 2.5'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': 'e.g., -8.9094'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': 'e.g., 33.4607'}),
            'google_maps_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://maps.app.goo.gl/...'}),
        }


class PropertyRentForm(forms.ModelForm):
    """Step 4 of the property wizard - rent and availability."""
    class Meta:
        model = Property
        fields = ['monthly_rent', 'amenities', 'min_months', 'max_months', 'months_per_payment']
        widgets = {
            'monthly_rent': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 150000'}),
            'amenities': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'water, electricity, wifi, parking'}),
            'min_months': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 3', 'min': 1}),
            'max_months': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 12', 'min': 1}),
            'months_per_payment': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }


class PropertyImageForm(forms.ModelForm):
    class Meta:
        model = PropertyImage
        fields = ['image', 'caption', 'is_primary']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'caption': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional caption'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }