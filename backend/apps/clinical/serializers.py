from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.drugs.models import Drug

from .models import Medication, PrescriptionScan


# ------------------------------------------------------------------------------------------------ scan upload
class ScanUploadSerializer(serializers.Serializer):
    """POST /api/prescriptions/scan/ (multipart). Ownership is NOT taken from here: `patient_id` is checked against the user.

    The file's real type and size are checked in services.create_scan from its bytes, not from the client's headers.
    """

    patient_id = serializers.IntegerField(min_value=1)
    image = serializers.FileField(allow_empty_file=False, max_length=255)


class ScanUploadResponseSerializer(serializers.Serializer):
    scan_id = serializers.IntegerField()
    status = serializers.CharField()
    idempotent_replay = serializers.BooleanField()
    retain_until = serializers.DateTimeField()


# ------------------------------------------------------------------------------------------------ drafts
class ResolutionHintSerializer(serializers.Serializer):
    """Basis of an automatic match, or suggestions for an unresolved row. Suggestions are never applied automatically."""

    status = serializers.CharField(required=False)
    generic = serializers.CharField(required=False)
    confidence = serializers.FloatField(required=False)
    match_type = serializers.CharField(required=False)
    verified = serializers.BooleanField(required=False)
    reason = serializers.CharField(required=False)
    candidates = serializers.ListField(child=serializers.CharField(), required=False)


class DraftMedicationSerializer(serializers.ModelSerializer):
    """One row of the Review & Confirm list. `drug` comes from select_related, so a list costs no extra queries."""

    generic_name = serializers.SerializerMethodField()
    resolution = serializers.SerializerMethodField()

    class Meta:
        model = Medication
        fields = ["id", "patient", "scan", "raw_text", "brand_name", "strength", "frequency", "drug", "generic_name",
                  "resolution_status", "confirmed_by_user", "source", "resolution", "created_at"]
        read_only_fields = fields

    def get_generic_name(self, obj) -> str | None:
        return obj.drug.generic_name if obj.drug_id else None

    @extend_schema_field(ResolutionHintSerializer(allow_null=True))
    def get_resolution(self, obj):
        return self.context.get("hints", {}).get(obj.id)


class MedicationUpdateSerializer(serializers.Serializer):
    """PATCH /api/medications/{id}/ — edit and/or confirm one medication (the Review & Confirm step).

    * `drug_id` is the generic the person picked (null = clear it). Omit it to leave the drug alone.
    * Changing `raw_text` or `brand_name` WITHOUT a `drug_id` clears the drug: pick or resolve again.
    * `confirmed_by_user: true` = a person reviewed this row. Any edit without it resets the confirmation.
    """

    raw_text = serializers.CharField(max_length=200, required=False, allow_blank=False)
    brand_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    strength = serializers.CharField(max_length=40, required=False, allow_blank=True)
    frequency = serializers.CharField(max_length=60, required=False, allow_blank=True)
    drug_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    confirmed_by_user = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Send at least one field to change.")
        if "drug_id" in attrs:
            drug_id = attrs.pop("drug_id")
            drug = None
            if drug_id is not None:
                drug = Drug.objects.filter(pk=drug_id).first()
                if drug is None:
                    raise serializers.ValidationError({"drug_id": "Unknown drug id."})
            attrs["drug"] = drug
        return attrs


# ------------------------------------------------------------------------------------------------ scan detail
class ScanDetailSerializer(serializers.ModelSerializer):
    """GET /api/prescriptions/scan/{id}/ — poll while queued/processing, read the draft list once `extracted`.

    While the scan is not `extracted` the clinical fields are `null`: a partial extraction never looks final.
    The image itself is never part of this response (no URL exists); use GET .../image/ (authenticated, audited).
    """

    scan_id = serializers.IntegerField(source="id", read_only=True)
    patient_id = serializers.IntegerField(read_only=True)
    is_final = serializers.SerializerMethodField()
    image_available = serializers.SerializerMethodField()
    requires_confirmation = serializers.SerializerMethodField()
    legibility = serializers.SerializerMethodField()
    drafts = serializers.SerializerMethodField()
    disclaimer_version = serializers.SerializerMethodField()

    class Meta:
        model = PrescriptionScan
        fields = ["scan_id", "patient_id", "status", "is_final", "error_code", "retain_until", "image_available",
                  "requires_confirmation", "legibility", "drafts", "created_at", "disclaimer_version"]
        read_only_fields = fields

    def _ready(self, obj) -> bool:
        return obj.status == "extracted" and "drafts" in self.context

    def get_is_final(self, obj) -> bool:
        return obj.status in ("extracted", "failed")

    def get_image_available(self, obj) -> bool:
        return bool(obj.image)

    def get_requires_confirmation(self, obj) -> bool:
        # Extracted rows are drafts. The person must review every row before an analysis can start.
        return obj.status == "extracted"

    def get_legibility(self, obj) -> str | None:
        return (obj.extracted_json or {}).get("legibility") if self._ready(obj) else None

    @extend_schema_field(DraftMedicationSerializer(many=True, allow_null=True))
    def get_drafts(self, obj):
        if not self._ready(obj):
            return None
        return DraftMedicationSerializer(self.context["drafts"], many=True, context=self.context).data

    def get_disclaimer_version(self, obj) -> str:
        return settings.DISCLAIMER_VERSION