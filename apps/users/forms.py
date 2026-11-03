import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import User

# Self-registration must never be able to grant ADMIN - User.ROLE_CHOICES
# includes it because it's also used for display/admin purposes elsewhere
# (e.g. the Django admin's own role dropdown), but this form's choices are
# deliberately a separate, narrower list.
REGISTRATION_ROLE_CHOICES = [
    choice for choice in User.ROLE_CHOICES if choice[0] in ('TENANT', 'LANDLORD')
]


def normalize_phone(value):
    """Accept everyday formats ('+255 712 345 678', '0712-345-678') and store
    just digits with an optional leading '+', which fits User.phone's 15
    chars - spaces alone used to push valid numbers past that limit."""
    phone = re.sub(r'[\s\-().]', '', value or '')
    if phone and not re.fullmatch(r'\+?\d{9,14}', phone):
        raise ValidationError("Enter a valid phone number, e.g. 0712345678 or +255712345678.")
    return phone


class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(choices=REGISTRATION_ROLE_CHOICES, required=True)
    phone = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'role', 'phone']

    def clean_phone(self):
        return normalize_phone(self.cleaned_data['phone'])


class ProfileForm(forms.ModelForm):
    # Declared explicitly so the model's max_length=15 isn't checked before
    # clean_phone strips separators - it's still enforced on the cleaned
    # value by the model validation that runs afterwards.
    phone = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['email', 'phone']

    def clean_phone(self):
        return normalize_phone(self.cleaned_data.get('phone'))
