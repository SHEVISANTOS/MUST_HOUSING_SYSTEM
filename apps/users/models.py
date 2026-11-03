from django.contrib.auth.models import AbstractUser
from django.db import models
from config.uploads import RandomName, validate_image_upload

class User(AbstractUser):
    ROLE_CHOICES = [
        ('LANDLORD', 'Landlord'),
        ('TENANT', 'Tenant'),
        ('ADMIN', 'Admin'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='TENANT')
    phone = models.CharField(max_length=15, blank=True)
    is_verified = models.BooleanField(default=False)
    profile_picture = models.ImageField(blank=True, null=True, upload_to=RandomName('profile_pics'), validators=[validate_image_upload])

    def __str__(self):
        return f"{self.username} ({self.role})"
