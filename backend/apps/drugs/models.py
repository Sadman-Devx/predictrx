from django.db import models
from django.db.models import F, Q


class Drug(models.Model):
    generic_name = models.CharField(max_length=150, unique=True)  # normalized lower-case
    aliases = models.JSONField(default=list, blank=True)
    external_ids = models.JSONField(default=dict, blank=True)

    def save(self, *args, **kwargs):
        self.generic_name = self.generic_name.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.generic_name


class BrandMapping(models.Model):
    """Local-naming layer. `verified` stays False until a pharmacist/mentor reviews the row."""

    brand_name = models.CharField(max_length=120, db_index=True)
    strength = models.CharField(max_length=40, blank=True)
    dosage_form = models.CharField(max_length=30, blank=True)
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="brands")
    source = models.CharField(max_length=60)  # where the mapping came from (required)
    verified = models.BooleanField(default=False)
    confidence = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.brand_name} → {self.drug}"


class Interaction(models.Model):
    SEVERITY = [("minor", "Minor"), ("moderate", "Moderate"), ("major", "Major"), ("unknown", "Unknown")]

    # Stored with canonical order: drug_a.id < drug_b.id
    drug_a = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name="interactions_as_a")
    drug_b = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name="interactions_as_b")
    severity = models.CharField(max_length=10, choices=SEVERITY, default="unknown")
    mechanism = models.TextField(blank=True)
    management = models.TextField(blank=True)
    source = models.CharField(max_length=30)  # e.g. ddinter
    source_ref = models.CharField(max_length=200, blank=True)
    license_note = models.CharField(max_length=120, blank=True)  # e.g. "CC BY-NC-SA 4.0 — non-commercial"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["drug_a", "drug_b", "source"], name="uniq_interaction_pair_source"),
            models.CheckConstraint(condition=Q(drug_a__lt=F("drug_b")), name="interaction_canonical_order"),
        ]
        indexes = [models.Index(fields=["drug_a", "drug_b"])]

    @classmethod
    def canonical(cls, a_id: int, b_id: int) -> tuple[int, int]:
        return (a_id, b_id) if a_id < b_id else (b_id, a_id)
