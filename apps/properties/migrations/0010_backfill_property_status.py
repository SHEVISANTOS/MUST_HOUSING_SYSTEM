from django.db import migrations


def backfill_status(apps, schema_editor):
    Property = apps.get_model('properties', 'Property')
    Property.objects.filter(is_available=True).update(status='live')
    Property.objects.filter(is_available=False).update(status='paused')


def noop_reverse(apps, schema_editor):
    # No reverse backfill - status didn't exist before this migration, so
    # there's nothing meaningful to restore it to.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('properties', '0009_property_max_months_property_min_months_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_status, noop_reverse),
    ]
