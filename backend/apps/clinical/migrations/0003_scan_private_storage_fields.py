import apps.clinical.models
import core.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0002_medication_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="prescriptionscan",
            name="content_type",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AddField(
            model_name="prescriptionscan",
            name="image_sha256",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="prescriptionscan",
            name="error_code",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="prescriptionscan",
            name="image_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="prescriptionscan",
            name="image",
            field=models.FileField(
                storage=core.storage.get_private_storage,
                upload_to=apps.clinical.models.scan_upload_path,
            ),
        ),
        migrations.AlterField(
            model_name="prescriptionscan",
            name="retain_until",
            field=models.DateTimeField(db_index=True),
        ),
    ]