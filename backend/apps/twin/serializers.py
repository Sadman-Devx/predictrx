"""Request / response shapes of the what-if (Digital Twin) API.

Finding cards deliberately reuse the field names of `apps.analysis.serializers.RiskFindingSerializer`
(drug_a, drug_b, entered_names_a/b, severity, rationale, confidence, confidence_basis, verification_status,
evidence) so the frontend can render them with the same FindingCard component as the main results.
"""
from rest_framework import serializers

from apps.analysis.serializers import (ConfidenceBasisSerializer, DisclaimerSerializer, EvidenceItemSerializer,
                                       GapSerializer)


# ------------------------------------------------------------------------------------------------ request
class TwinStartSerializer(serializers.Serializer):
    """POST /api/twin/ body. Ownership is NOT taken from here: `base_run_id` is checked against the user.

    Send exactly one of `drug_id` or `generic_name` (the drug to add hypothetically).
    """

    base_run_id = serializers.IntegerField(min_value=1)
    drug_id = serializers.IntegerField(min_value=1, required=False)
    generic_name = serializers.CharField(max_length=120, required=False, allow_blank=False, trim_whitespace=True)

    def validate(self, attrs):
        has_id, has_name = "drug_id" in attrs, "generic_name" in attrs
        if has_id == has_name:
            raise serializers.ValidationError("Send exactly one of 'drug_id' or 'generic_name'.")
        return attrs


# ------------------------------------------------------------------------------------------------ building blocks
class TwinDrugRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    generic_name = serializers.CharField()


class TwinBaseDrugSerializer(TwinDrugRefSerializer):
    entered_names = serializers.ListField(child=serializers.CharField())


class TwinFindingSerializer(serializers.Serializer):
    """A finding the added drug introduces. `evidence` is never empty for a severity other than `unknown`."""

    drug_a = TwinDrugRefSerializer()
    drug_b = TwinDrugRefSerializer()
    entered_names_a = serializers.ListField(child=serializers.CharField())
    entered_names_b = serializers.ListField(child=serializers.CharField())
    severity = serializers.ChoiceField(choices=["major", "moderate", "minor", "unknown"])
    rationale = serializers.CharField(allow_blank=True)
    management = serializers.CharField(allow_null=True)
    confidence = serializers.FloatField()
    confidence_basis = ConfidenceBasisSerializer()
    verification_status = serializers.ChoiceField(choices=["verified", "unverified", "conflict"])
    evidence = EvidenceItemSerializer(many=True)
    pair_status = serializers.CharField()  # always "record" for an added finding
    severity_conflict = serializers.BooleanField()


class TwinNoRecordSerializer(serializers.Serializer):
    """A pair with no interaction record. NEVER "safe": `note` says so."""

    drug_a = TwinDrugRefSerializer()
    drug_b = TwinDrugRefSerializer()
    entered_names_a = serializers.ListField(child=serializers.CharField())
    entered_names_b = serializers.ListField(child=serializers.CharField())
    pair_status = serializers.CharField()  # always "no_record"
    note = serializers.CharField()


class SeverityCountsSerializer(serializers.Serializer):
    major = serializers.IntegerField()
    moderate = serializers.IntegerField()
    minor = serializers.IntegerField()
    unknown = serializers.IntegerField()


class SeverityPictureSerializer(serializers.Serializer):
    highest_severity = serializers.CharField(allow_null=True)  # null = no known severity at all
    counts = SeverityCountsSerializer()
    total = serializers.IntegerField()


class TwinComparisonSerializer(serializers.Serializer):
    before = SeverityPictureSerializer()
    after = SeverityPictureSerializer()
    highest_severity_changed = serializers.BooleanField()
    base_findings_count = serializers.IntegerField()
    new_findings_count = serializers.IntegerField()
    pairs_checked = serializers.IntegerField()


class SimulationNoteSerializer(serializers.Serializer):
    text_en = serializers.CharField()
    text_bn = serializers.CharField()


# ------------------------------------------------------------------------------------------------ response
class TwinScenarioSerializer(serializers.Serializer):
    """One stored what-if scenario. `simulation` is always true: the UI must label it as a simulation.

    `limitations` are machine codes for the UI to translate:
      interaction_table_only · labs_vitals_not_used · label_passages_not_searched · unresolved_medications_not_checked
    """

    scenario_id = serializers.IntegerField()
    base_run_id = serializers.IntegerField()
    patient_id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    simulation = serializers.BooleanField()
    simulation_note = SimulationNoteSerializer()
    hypothetical_drug = TwinDrugRefSerializer()
    base_drugs = TwinBaseDrugSerializer(many=True)
    added_findings = TwinFindingSerializer(many=True)
    no_record_pairs = TwinNoRecordSerializer(many=True)
    comparison = TwinComparisonSerializer()
    gaps = GapSerializer(many=True)
    limitations = serializers.ListField(child=serializers.CharField())
    guardrail_violations = serializers.ListField(child=serializers.CharField())
    disclaimer_version = serializers.CharField()
    disclaimer = DisclaimerSerializer()


class TwinScenarioSummarySerializer(serializers.Serializer):
    scenario_id = serializers.IntegerField()
    hypothetical_drug = TwinDrugRefSerializer()
    created_at = serializers.DateTimeField()
    new_findings_count = serializers.IntegerField()
    highest_severity_after = serializers.CharField(allow_null=True)
    highest_severity_changed = serializers.BooleanField()


class TwinListSerializer(serializers.Serializer):
    base_run_id = serializers.IntegerField()
    results = TwinScenarioSummarySerializer(many=True)
