from rest_framework import serializers

from .models import Drug, Interaction


class DrugSerializer(serializers.ModelSerializer):
    class Meta:
        model = Drug
        fields = ["id", "generic_name", "aliases"]
        read_only_fields = fields


class DrugDetailSerializer(serializers.ModelSerializer):
    sources = serializers.SerializerMethodField(help_text="Knowledge sources that hold a document for this drug.")

    class Meta:
        model = Drug
        fields = ["id", "generic_name", "aliases", "external_ids", "sources"]
        read_only_fields = fields

    def get_sources(self, obj) -> list[str]:
        return sorted({doc.source for doc in obj.documents.all()})  # prefetched: no N+1


class DrugRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Drug
        fields = ["id", "generic_name"]
        read_only_fields = fields


class InteractionSerializer(serializers.ModelSerializer):
    """source, source_ref, license_note are always present. No record found does NOT mean safe."""

    drug_a = DrugRefSerializer(read_only=True)
    drug_b = DrugRefSerializer(read_only=True)

    class Meta:
        model = Interaction
        fields = ["id", "drug_a", "drug_b", "severity", "mechanism", "management",
                  "source", "source_ref", "license_note"]
        read_only_fields = fields

class ResolveRequestSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.CharField(max_length=120, allow_blank=True),
                                  min_length=1, max_length=20)


class CheckRequestSerializer(serializers.Serializer):
    drugs = serializers.ListField(child=serializers.CharField(max_length=120), min_length=2, max_length=12)
