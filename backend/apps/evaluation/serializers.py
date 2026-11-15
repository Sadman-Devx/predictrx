from rest_framework import serializers

from .models import EvalRun


class EvalStartSerializer(serializers.Serializer):
    """POST /api/eval/run/ body. `test` is the number you report; use `dev` while you are still tuning."""

    split = serializers.ChoiceField(choices=["dev", "test"], default="test")


class EvalStartResponseSerializer(serializers.Serializer):
    run_id = serializers.IntegerField()
    status = serializers.CharField()
    split = serializers.CharField()
    n_cases = serializers.IntegerField()


class EvalRunSerializer(serializers.ModelSerializer):
    """Read-only view of a run. `metrics` is empty until the run is `completed`; a failed run never has metrics."""

    class Meta:
        model = EvalRun
        fields = ("id", "kind", "split", "status", "error_code", "n_cases", "fingerprint", "metrics", "config",
                  "created_at", "started_at", "finished_at")
        read_only_fields = fields