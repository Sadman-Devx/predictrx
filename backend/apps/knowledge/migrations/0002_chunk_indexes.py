from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="chunk",
            index=models.Index(fields=["document", "section"], name="chunk_doc_section_idx"),
        ),
        migrations.AddIndex(
            model_name="chunk",
            index=models.Index(
                condition=models.Q(("embedding__isnull", True)),
                fields=["id"],
                name="chunk_unembedded_idx",
            ),
        ),
    ]