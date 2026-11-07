from django.conf import settings
from django.db import models

from apps.drugs.models import Drug
from apps.patients.models import Patient
from core.exceptions import OutOfEvidence


class AnalysisRun(models.Model):
    STATUS = [("queued", "Queued"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")]

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="runs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="runs")
    idempotency_key = models.CharField(max_length=64, unique=True)  # one click = one run
    status = models.CharField(max_length=12, choices=STATUS, default="queued")
    input_snapshot = models.JSONField(default=dict)  # frozen, redacted inputs at run time
    model_info = models.JSONField(default=dict)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["patient", "started_at"])]


class AgentTrace(models.Model):
    AGENTS = [("resolver", "Resolver"), ("clinical_notes", "Clinical Notes"), ("drug_interaction", "Drug Interaction"),
              ("advisory", "Advisory"), ("verifier", "Verifier")]

    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="traces")
    agent_name = models.CharField(max_length=30, choices=AGENTS)
    step_order = models.PositiveSmallIntegerField()
    input_summary = models.TextField(blank=True)   # redacted
    output_summary = models.TextField(blank=True)  # redacted
    tool_calls = models.JSONField(default=list, blank=True)
    latency_ms = models.IntegerField(default=0)

    class Meta:
        ordering = ["run", "step_order"]


class RiskFinding(models.Model):
    SEVERITY = [("minor", "Minor"), ("moderate", "Moderate"), ("major", "Major"), ("unknown", "Unknown")]
    VERIFICATION = [("verified", "Verified"), ("unverified", "Unverified"), ("conflict", "Conflict")]

    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="findings")
    drug_a = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="+")
    drug_b = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="+")
    severity = models.CharField(max_length=10, choices=SEVERITY, default="unknown")
    rationale = models.TextField(blank=True)
    confidence = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    verification_status = models.CharField(max_length=12, choices=VERIFICATION, default="unverified")
    # [{"type": "interaction"|"chunk", "id": 12, "source": "ddinter"}]  — required unless severity == unknown
    evidence = models.JSONField(default=list, blank=True)

    def save(self, *args, **kwargs):
        # Rule: no warning without a source. Enforced at the model level so no code path can bypass it.
        if self.severity != "unknown" and not self.evidence:
            raise OutOfEvidence("A finding with a severity must carry evidence; otherwise use severity 'unknown'.")
        super().save(*args, **kwargs)


class RiskSummary(models.Model):
    run = models.OneToOneField(AnalysisRun, on_delete=models.CASCADE, related_name="summary")
    doctor_summary_bn = models.TextField(blank=True)
    doctor_summary_en = models.TextField(blank=True)
    patient_card_bn = models.TextField(blank=True)  # plain language, no dosing
    disclaimer_version = models.CharField(max_length=10, default="v1")
