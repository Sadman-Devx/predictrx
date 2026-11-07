from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=40)  # patient_read | analysis_start | family_view | consent_change | image_access
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    patient = models.ForeignKey("patients.Patient", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    ip = models.GenericIPAddressField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)  # never put PII here
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["patient", "at"])]
