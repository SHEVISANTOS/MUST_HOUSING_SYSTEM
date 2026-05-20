from django import forms
from .models import Payment

class TenantPaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['payment_method', 'payment_reference', 'payment_proof', 'payment_notes']
        widgets = {
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'payment_reference': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., QKH123456789 (M-Pesa code) or Bank Ref'
            }),
            'payment_proof': forms.FileInput(attrs={'class': 'form-control'}),
            'payment_notes': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'placeholder': 'Optional: Date paid, branch, etc.'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_reference'].required = False
        self.fields['payment_proof'].required = False


class LandlordConfirmForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="I confirm I have received this payment offline",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    confirmation_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes (e.g., "Received cash on 15-May")'
        }),
        label="Confirmation Notes"
    )