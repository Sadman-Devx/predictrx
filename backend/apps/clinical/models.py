import uuid

from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.drugs.models import Drug
from apps.patients.models import Patient
from core.storage import get_private_storage

_IMAGE_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def scan_upload_path(instance, filename):
    """Random name, never the client's filename (it can contain a patient's name). Extension comes from the sniffed type."""
    ext = _IMAGE_EXT.get(instance.content_type, "bin")
    return f"prescriptions/{instance.patient_id}/{uuid.uuid4().hex}.{ext}"


class PrescriptionScan(models.Model):
    STATUS = [("queued", "Queued"), ("processing", "Processing"), ("extracted", "Extracted"), ("failed", "Failed")]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="scans")
    # Private storage: no public URL exists for this file (core/storage.py). Served only by an owner-checked, audited view.
    image = models.FileField(storage=get_private_storage, upload_to=scan_upload_path)
    content_type = models.CharField(max_length=30, blank=True, default="")  # sniffed from the file's bytes, not trusted from the client
    image_sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)  # same image twice -> one scan
    status = models.CharField(max_length=15, choices=STATUS, default="queued")
    error_code = models.CharField(max_length=40, blank=True, default="")  # why a scan failed (machine code, no text from the image)
    extracted_json = models.JSONField(default=dict, blank=True)  # validated DRAFT only (no raw model text, no PII)
    retain_until = models.DateTimeField(db_index=True)
    image_deleted_at = models.DateTimeField(null=True, blank=True)  # set when the file was removed (early delete or retention)
    created_at = models.DateTimeField(auto_now_add=True)


@receiver(post_delete, sender=PrescriptionScan)
def delete_image_with_row(sender, instance, **kwargs):
    """A scan row can disappear (admin, cascade from a patient). Its private image file must go with it, not linger."""
    name, storage = instance.image.name, instance.image.storage
    if name:
        transaction.on_commit(lambda: storage.delete(name))  # only after the delete is really committed


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
    created_at = models.DateTimeField(default=timezone.now, editable=False)


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