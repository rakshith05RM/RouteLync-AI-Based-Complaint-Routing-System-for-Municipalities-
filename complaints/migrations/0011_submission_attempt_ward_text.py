from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("complaints", "0010_optional_location_ward_and_area"),
        ("departments", "0002_area_service_district"),
    ]

    operations = [
        migrations.AddField(
            model_name="submissionattempt",
            name="ward_text",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
