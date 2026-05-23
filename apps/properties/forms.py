# apps/properties/forms.py

from django import forms
from .models import Property, PropertyImage

class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = [
            'title', 'description', 'property_type', 'location',
            'distance_from_must_km', 'monthly_rent', 'amenities',
            'latitude', 'longitude', 'google_maps_link', 'is_available'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Spacious 2BR near MUST'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe your property...'}),
            'property_type': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Iyunga, Mbeya'}),
            'distance_from_must_km': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'monthly_rent': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 150000'}),
            'amenities': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'water, electricity, wifi, parking'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': 'e.g., -8.9094'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': 'e.g., 33.4607'}),
            'google_maps_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://maps.app.goo.gl/...'}),
            'is_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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