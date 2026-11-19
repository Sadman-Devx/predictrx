from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]