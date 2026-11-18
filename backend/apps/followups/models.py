from django.conf import settings
from django.db import models


class FollowUpTask(models.Model):
    TASK_TYPES = [
        ("review_analysis", "Review analysis"),
        ("patient_contact", "Contact patient"),
        ("medication_reconciliation", "Medication reconciliation"),
        ("follow_up_visit", "Follow-up visit"),
    ]
    STATUSES = [
        ("to_review", "To review"),
        ("in_progress", "In progress"),
        ("done", "Done"),
    ]

    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="follow_up_tasks")
    analysis_run = models.ForeignKey(
        "analysis.AnalysisRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="follow_up_tasks"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_follow_ups"
    )
    task_type = models.CharField(max_length=32, choices=TASK_TYPES)
    status = models.CharField(max_length=16, choices=STATUSES, default="to_review")
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "-created_at"]
        indexes = [
            models.Index(fields=["patient", "status", "due_date"], name="fu_patient_status_due_idx"),
        ]
