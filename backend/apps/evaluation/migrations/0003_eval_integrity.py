"""Schema step: integrity constraints on EvalCase + bookkeeping fields on EvalRun.

`status` is added with default "completed" (any run that exists before this migration already finished) and then
altered to the real default "queued", so old rows stay truthful and new rows start queued.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("evaluation", "0002_eval_prepare_cases"),
    ]

    operations = [
        # ---- EvalCase
        migrations.AlterField(
            model_name="evalcase",
            name="expected_severity",
            field=models.CharField(
                choices=[("none", "No interaction (reviewer)"), ("minor", "Minor"), ("moderate", "Moderate"),
                         ("major", "Major")],
                max_length=10,
            ),
        ),
        migrations.AddConstraint(
            model_name="evalcase",
            constraint=models.UniqueConstraint(fields=("drug_a", "drug_b"), name="uniq_evalcase_pair"),
        ),
        migrations.AddConstraint(
            model_name="evalcase",
            constraint=models.CheckConstraint(
                condition=models.Q(drug_a__lt=models.F("drug_b")), name="evalcase_canonical_order"),
        ),
        migrations.AddConstraint(
            model_name="evalcase",
            constraint=models.CheckConstraint(
                condition=models.Q(expected_severity__in=["none", "minor", "moderate", "major"]),
                name="evalcase_valid_severity"),
        ),
        # ---- EvalRun
        migrations.AddField(
            model_name="evalrun",
            name="kind",
            field=models.CharField(choices=[("pairs", "Drug pairs"), ("brands", "Brand resolution")],
                                   default="pairs", max_length=10),
        ),
        migrations.AddField(
            model_name="evalrun",
            name="split",
            field=models.CharField(blank=True, default="", max_length=5),
        ),
        migrations.AddField(
            model_name="evalrun",
            name="status",
            field=models.CharField(
                choices=[("queued", "Queued"), ("running", "Running"), ("completed", "Completed"),
                         ("failed", "Failed")],
                default="completed", max_length=10),
        ),
        migrations.AlterField(
            model_name="evalrun",
            name="status",
            field=models.CharField(
                choices=[("queued", "Queued"), ("running", "Running"), ("completed", "Completed"),
                         ("failed", "Failed")],
                default="queued", max_length=10),
        ),
        migrations.AddField(
            model_name="evalrun",
            name="error_code",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="evalrun",
            name="fingerprint",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="evalrun",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="evalrun",
            name="finished_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="evalrun",
            name="created_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+",
                to=settings.AUTH_USER_MODEL),
        ),
    ]