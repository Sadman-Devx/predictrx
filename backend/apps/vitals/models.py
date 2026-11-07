import hashlib
import secrets

from django.db import models


class Device(models.Model):
    device_id = models.CharField(max_length=64, unique=True)
    token_hash = models.CharField(max_length=64, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.device_id

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def create_with_token(cls, device_id: str):
        """Returns (device, plain_token). Plain token is shown only once."""
        token = secrets.token_urlsafe(32)
        device = cls.objects.create(device_id=device_id, token_hash=cls.hash_token(token))
        return device, token


class VitalReading(models.Model):
    SEVERITY = [("normal", "Normal"), ("warning", "Warning"), ("critical", "Critical")]

    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="readings")
    # Keep loose coupling. Swap for ForeignKey("patients.Patient") when the model exists.
    patient_id = models.CharField(max_length=64, db_index=True)
    spo2 = models.PositiveSmallIntegerField()
    pulse = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=16, default="esp32")  # esp32 | simulated | manual
    severity = models.CharField(max_length=10, choices=SEVERITY, default="normal")
    alert_reason = models.CharField(max_length=200, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [models.Index(fields=["patient_id", "-recorded_at"])]

    def __str__(self):
        return f"{self.patient_id} SpO2={self.spo2} HR={self.pulse}"
