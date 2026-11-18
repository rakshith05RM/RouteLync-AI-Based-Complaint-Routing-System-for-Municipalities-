from django.db import migrations, models
import django.db.models.deletion


def backfill_area(apps, schema_editor):
    Area = apps.get_model("departments", "Area")
    ComplaintLocation = apps.get_model("complaints", "ComplaintLocation")
    SubmissionAttempt = apps.get_model("complaints", "SubmissionAttempt")
    database = schema_editor.connection.alias
    for name in ("Bengaluru Urban", "Bengaluru Rural"):
        Area.objects.using(database).get_or_create(name=name)
    for model in (ComplaintLocation, SubmissionAttempt):
        records = (model.objects.using(database).filter(area__isnull=True, ward__isnull=False)
                   .select_related("ward").iterator(chunk_size=1000))
        for record in records:
            record.area_id = record.ward.area_id
            record.save(update_fields=["area"])


class Migration(migrations.Migration):

    dependencies = [
        ("complaints", "0009_location_selection"),
        ("departments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="submissionattempt",
            name="area",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="+", to="departments.area"),
        ),
        migrations.AddField(
            model_name="complaintlocation",
            name="area",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="complaint_locations", to="departments.area"),
        ),
        migrations.AlterField(
            model_name="complaintlocation",
            name="ward",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="complaint_locations", to="departments.ward"),
        ),
        migrations.AlterField(
            model_name="complaintlocation",
            name="street",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.RunPython(backfill_area, migrations.RunPython.noop),
    ]
