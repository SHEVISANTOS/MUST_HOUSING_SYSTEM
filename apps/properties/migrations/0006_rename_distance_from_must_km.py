from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('properties', '0005_property_google_maps_link_property_latitude_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='property',
            old_name='distance_from_must_km',
            new_name='distance_from_center_km',
        ),
        migrations.AlterField(
            model_name='property',
            name='distance_from_center_km',
            field=models.FloatField(help_text='Distance in km from city center'),
        ),
    ]
