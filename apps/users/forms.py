from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

# Self-registration must never be able to grant ADMIN - User.ROLE_CHOICES
# includes it because it's also used for display/admin purposes elsewhere
# (e.g. the Django admin's own role dropdown), but this form's choices are
# deliberately a separate, narrower list.
REGISTRATION_ROLE_CHOICES = [
    choice for choice in User.ROLE_CHOICES if choice[0] in ('TENANT', 'LANDLORD')
]


class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(choices=REGISTRATION_ROLE_CHOICES, required=True)
    phone = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'role', 'phone']