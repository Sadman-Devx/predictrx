from django.db import models

from apps.analysis.models import AnalysisRun
from apps.drugs.models import Drug
from apps.patients.models import Patient


class TwinScenario(models.Model):
    """What-if simulation: added/changed findings vs. a base run. Labelled as simulation in the UI."""

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="twin_scenarios")
    base_run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="twin_scenarios")
    hypothetical_drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="+")
    result_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
