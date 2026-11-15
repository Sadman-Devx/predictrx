from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.drugs.models import Drug

EXPECTED_SEVERITIES = ["none", "minor", "moderate", "major"]


class EvalCase(models.Model):
    """Labelled drug pair. The set must come from a source/reviewer INDEPENDENT of the RAG/Verifier data.

    Integrity rules (enforced by constraints, because a leaked pair would quietly inflate the test numbers):
      * stored in canonical order (drug_a.id < drug_b.id), so (A,B) and (B,A) are the same case;
      * one case per pair, so a pair can never sit in both `dev` and `test`;
      * `expected_severity` is the reviewer's label: none | minor | moderate | major ("none" = reviewer found
        no interaction; it is what makes precision measurable).
    """

    SPLIT = [("dev", "Dev"), ("test", "Test")]
    SEVERITY = [("none", "No interaction (reviewer)"), ("minor", "Minor"), ("moderate", "Moderate"), ("major", "Major")]

    drug_a = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="+")
    drug_b = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="+")
    expected_severity = models.CharField(max_length=10, choices=SEVERITY)
    rationale_ref = models.CharField(max_length=300)  # independent source note (required)
    reviewed_by = models.CharField(max_length=100, blank=True)
    split = models.CharField(max_length=5, choices=SPLIT, default="dev")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["drug_a", "drug_b"], name="uniq_evalcase_pair"),
            models.CheckConstraint(condition=Q(drug_a__lt=F("drug_b")), name="evalcase_canonical_order"),
            models.CheckConstraint(condition=Q(expected_severity__in=EXPECTED_SEVERITIES),
                                   name="evalcase_valid_severity"),
        ]

    def _canonicalise(self) -> None:
        if self.drug_a_id and self.drug_b_id and self.drug_a_id > self.drug_b_id:
            self.drug_a_id, self.drug_b_id = self.drug_b_id, self.drug_a_id

    def clean(self):
        self._canonicalise()  # runs before constraint validation, so the admin accepts (B, A) too
        if self.drug_a_id and self.drug_a_id == self.drug_b_id:
            raise ValidationError("A case needs two different drugs.")

    def save(self, *args, **kwargs):
        self._canonicalise()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.drug_a} + {self.drug_b}: {self.expected_severity} ({self.split})"


class EvalRun(models.Model):
    """One measured run. History: a finished run is never edited (admin is read-only).

    kind   pairs  -> detection metrics for the `split` of EvalCase
           brands -> brand-resolution metrics for a held-out CSV (no split)
    """

    KIND = [("pairs", "Drug pairs"), ("brands", "Brand resolution")]
    STATUS = [("queued", "Queued"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")]

    created_at = models.DateTimeField(auto_now_add=True)
    n_cases = models.IntegerField(default=0)
    metrics = models.JSONField(default=dict)  # recall, precision, per-severity (see metrics.py)
    config = models.JSONField(default=dict)  # how it was run: transport, data snapshot, caveats
    kind = models.CharField(max_length=10, choices=KIND, default="pairs")
    split = models.CharField(max_length=5, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS, default="queued")
    error_code = models.CharField(max_length=40, blank=True, default="")
    fingerprint = models.CharField(max_length=64, blank=True, default="")  # hash of the exact cases evaluated
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    def __str__(self):
        return f"EvalRun {self.pk} {self.kind}/{self.split or '-'} {self.status}"