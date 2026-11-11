from rest_framework import serializers


class ResolveRequestSerializer(serializers.Serializer):
    items = serializers.ListField(
        child=serializers.CharField(min_length=1, max_length=200, trim_whitespace=True),
        min_length=1,
        max_length=30,
    )


class ResolvedGenericSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class SuggestionSerializer(serializers.Serializer):
    brand_name = serializers.CharField()
    generic_id = serializers.IntegerField()
    generic_name = serializers.CharField()
    score = serializers.FloatField()


class ResolveResultSerializer(serializers.Serializer):
    input = serializers.CharField()
    status = serializers.ChoiceField(choices=["resolved", "unresolved"])
    match_type = serializers.ChoiceField(choices=["exact", "generic", "fuzzy", "none"])
    generic = ResolvedGenericSerializer(allow_null=True)
    confidence = serializers.FloatField()
    verified = serializers.BooleanField()
    source = serializers.CharField(allow_null=True)
    suggestions = SuggestionSerializer(many=True)
    reason = serializers.CharField(allow_null=True)


class ResolveResponseSerializer(serializers.Serializer):
    results = ResolveResultSerializer(many=True)


class DrugSearchItemSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["brand", "generic"])
    label = serializers.CharField()
    brand_name = serializers.CharField(allow_null=True)
    strength = serializers.CharField(allow_null=True)
    generic_id = serializers.IntegerField()
    generic_name = serializers.CharField()
    verified = serializers.BooleanField()


class DrugSearchResponseSerializer(serializers.Serializer):
    results = DrugSearchItemSerializer(many=True)