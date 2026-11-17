from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        # Accounts that exist today are treated as verified (they were created before verification existed),
        # so turning REQUIRE_EMAIL_VERIFICATION on never locks them out. New accounts start unverified.
        migrations.AddField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
    ]
