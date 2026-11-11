from rest_framework import serializers

from .services import MAX_INPUT_LEN, SEARCH_MAX_LIMIT

MAX_RESOLVE_ITEMS = 30


class ResolveItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=MAX_INPUT_LEN)
    strength = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


class ResolveRequestSerializer(serializers.Serializer):
    items = ResolveItemSerializer(many=True, allow_empty=False, max_length=MAX_RESOLVE_ITEMS)


class ResolveResultSerializer(serializers.Serializer):
    """Documentation only: `resolved` carries generic/confidence/verified/source/match_type; `unresolved` a reason."""

    status = serializers.ChoiceField(choices=["resolved", "unresolved"])
    input = serializers.CharField()
    generic = serializers.CharField(required=False)
    confidence = serializers.FloatField(required=False)
    verified = serializers.BooleanField(required=False)
    source = serializers.CharField(required=False)
    match_type = serializers.ChoiceField(choices=["exact", "generic", "fuzzy"], required=False)
    matched_name = serializers.CharField(required=False)
    strength = serializers.CharField(required=False, allow_blank=True)
    strength_matched = serializers.BooleanField(required=False, allow_null=True)
    aliases = serializers.ListField(child=serializers.CharField(), required=False)
    reason = serializers.CharField(required=False)
    candidates = serializers.ListField(child=serializers.CharField(), required=False)


class ResolveResponseSerializer(serializers.Serializer):
    results = ResolveResultSerializer(many=True)


class SearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=MAX_INPUT_LEN)
    limit = serializers.IntegerField(min_value=1, max_value=SEARCH_MAX_LIMIT, default=10)


class SearchResultSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["brand", "generic"])
    name = serializers.CharField()
    generic = serializers.CharField()
    strength = serializers.CharField(allow_blank=True)
    dosage_form = serializers.CharField(allow_blank=True)
    verified = serializers.BooleanField()
    source = serializers.CharField()


class InteractionDrugSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    generic_name = serializers.CharField()


class InteractionDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    drug_a = InteractionDrugSerializer()
    drug_b = InteractionDrugSerializer()
    severity = serializers.CharField()
    mechanism = serializers.CharField()
    management = serializers.CharField()
    source = serializers.CharField()
    source_ref = serializers.CharField()
    license_note = serializers.CharField()


class SearchResponseSerializer(serializers.Serializer):
    results = SearchResultSerializer(many=True)
