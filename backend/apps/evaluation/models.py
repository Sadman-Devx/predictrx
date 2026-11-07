from django.db import models

from apps.drugs.models import Drug


class EvalCase(models.Model):
    """Labelled drug pair. The set must come from a source/reviewer INDEPENDENT of the RAG/Verifier data."""

    SPLIT = [("dev", "Dev"), ("test", "Test")]

    drug_a = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="+")
    drug_b = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="+")
    expected_severity = models.CharField(max_length=10)
    rationale_ref = models.CharField(max_length=300)  # independent source note (required)
    reviewed_by = models.CharField(max_length=100, blank=True)
    split = models.CharField(max_length=5, choices=SPLIT, default="dev")


class EvalRun(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    n_cases = models.IntegerField(default=0)
    metrics = models.JSONField(default=dict)  # recall, precision, per-severity
    config = models.JSONField(default=dict)
