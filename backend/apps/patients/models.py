from django.conf import settings
from django.db import models


class Patient(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="patients")
    # Pseudonymous label shown in the UI. Real names are not required.
    patient_code = models.CharField(max_length=20, unique=True)
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=10, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.patient_code


class Consent(models.Model):
    SCOPES = [("analysis", "Analysis"), ("family_view", "Family view"), ("retain_images", "Retain images")]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="consents")
    scope = models.CharField(max_length=20, choices=SCOPES)
    granted_by = models.CharField(max_length=100)
    granted_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_active(self):
        return self.revoked_at is None


class FamilyLink(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="family_links")
    family_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="family_links")
    relationship = models.CharField(max_length=30)
    consent = models.ForeignKey(Consent, on_delete=models.PROTECT, related_name="family_links")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("patient", "family_user")]
