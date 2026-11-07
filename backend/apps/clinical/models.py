from django.db import models

from apps.drugs.models import Drug
from apps.patients.models import Patient


class PrescriptionScan(models.Model):
    STATUS = [("queued", "Queued"), ("processing", "Processing"), ("extracted", "Extracted"), ("failed", "Failed")]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="scans")
    image = models.FileField(upload_to="prescriptions/")  # private storage, no public URL
    status = models.CharField(max_length=15, choices=STATUS, default="queued")
    extracted_json = models.JSONField(default=dict, blank=True)  # raw model output (draft)
    retain_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class Medication(models.Model):
    RESOLUTION = [("unresolved", "Unresolved"), ("resolved", "Resolved"), ("user_confirmed", "Confirmed by user")]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medications")
    scan = models.ForeignKey(PrescriptionScan, null=True, blank=True, on_delete=models.SET_NULL, related_name="medications")
    raw_text = models.CharField(max_length=200)  # exactly what was written / typed
    brand_name = models.CharField(max_length=120, blank=True)
    strength = models.CharField(max_length=40, blank=True)
    frequency = models.CharField(max_length=60, blank=True)  # informational only
    drug = models.ForeignKey(Drug, null=True, blank=True, on_delete=models.PROTECT, related_name="medications")
    resolution_status = models.CharField(max_length=14, choices=RESOLUTION, default="unresolved")
    confirmed_by_user = models.BooleanField(default=False)  # human-in-the-loop flag
    source = models.CharField(max_length=10, default="manual")  # scan | manual


class LabResult(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="labs")
    test_name = models.CharField(max_length=100)
    value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    ref_range = models.CharField(max_length=40, blank=True)
    recorded_at = models.DateTimeField()


class ClinicalNote(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="notes")
    text_redacted = models.TextField()  # PII-redacted copy used by agents
    created_at = models.DateTimeField(auto_now_add=True)
