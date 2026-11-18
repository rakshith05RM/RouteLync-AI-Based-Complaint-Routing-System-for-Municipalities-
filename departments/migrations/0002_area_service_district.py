from django.db import migrations, models


URBAN_AREAS = (
    "North Corporation",
    "South Corporation",
    "Central Corporation",
    "East Corporation",
    "West Corporation",
)
RURAL_TALUKS = (
    "Devanahalli Taluk",
    "Doddaballapura Taluk",
    "Hoskote Taluk",
    "Nelamangala Taluk",
)
LEGACY_URBAN_LOCALITIES = ("Jayanagar", "Indiranagar", "Rajajinagar", "Whitefield")


def seed_service_areas(apps, schema_editor):
    Area = apps.get_model("departments", "Area")
    database = schema_editor.connection.alias
    Area.objects.using(database).filter(name__in=LEGACY_URBAN_LOCALITIES).update(
        service_district="Bengaluru Urban")
    for name in URBAN_AREAS:
        Area.objects.using(database).update_or_create(
            name=name, defaults={"service_district": "Bengaluru Urban"})
    for name in RURAL_TALUKS:
        Area.objects.using(database).update_or_create(
            name=name, defaults={"service_district": "Bengaluru Rural"})


class Migration(migrations.Migration):

    dependencies = [
        ("departments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="area",
            name="service_district",
            field=models.CharField(
                blank=True,
                choices=[("Bengaluru Urban", "Bengaluru Urban"), ("Bengaluru Rural", "Bengaluru Rural")],
                max_length=20,
            ),
        ),
        migrations.RunPython(seed_service_areas, migrations.RunPython.noop),
    ]
