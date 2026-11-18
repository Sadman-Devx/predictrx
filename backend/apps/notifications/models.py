from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    EVENTS = [
        ("scan_ready", "Prescription scan ready for review"),
        ("scan_failed", "Prescription scan failed"),
        ("analysis_ready", "Analysis finished"),
        ("analysis_failed", "Analysis failed"),
    ]

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    event = models.CharField(max_length=20, choices=EVENTS)
    scan = models.ForeignKey(
        "clinical.PrescriptionScan", null=True, blank=True, on_delete=models.CASCADE, related_name="notifications"
    )
    analysis_run = models.ForeignKey(
        "analysis.AnalysisRun", null=True, blank=True, on_delete=models.CASCADE, related_name="notifications"
    )
    deduplication_key = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"], name="notif_recipient_date_idx"),
            models.Index(fields=["recipient", "read_at"], name="notif_recipient_read_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(event__in=["scan_ready", "scan_failed"], scan__isnull=False, analysis_run__isnull=True)
                    | Q(event__in=["analysis_ready", "analysis_failed"], scan__isnull=True, analysis_run__isnull=False)
                ),
                name="notification_target_matches_event",
            )
        ]

    @property
    def patient_id(self):
        if self.scan_id:
            return self.scan.patient_id
        if self.analysis_run_id:
            return self.analysis_run.patient_id
        return None
