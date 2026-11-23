"""Listings are now only public once the landlord is verified (see
Property.objects.public()). Landlords who already had live listings before
that rule existed are marked verified, so their homes don't vanish from
search on deploy. Anyone who signs up from now on goes through the queue."""
from django.db import migrations


def grandfather(apps, schema_editor):
    Property = apps.get_model('properties', 'Property')
    User = apps.get_model('users', 'User')
    ids = Property.objects.filter(is_available=True).values_list('landlord_id', flat=True)
    User.objects.filter(id__in=ids, is_verified=False).update(is_verified=True)


class Migration(migrations.Migration):
    dependencies = [
        ('properties', '0012_alter_propertyimage_image'),
        ('users', '0003_alter_user_profile_picture'),
    ]
    operations = [migrations.RunPython(grandfather, migrations.RunPython.noop)]
