from rest_framework import serializers


class ResolveRequestSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.CharField(max_length=120, allow_blank=True),
                                  min_length=1, max_length=20)


class CheckRequestSerializer(serializers.Serializer):
    drugs = serializers.ListField(child=serializers.CharField(max_length=120), min_length=2, max_length=12)