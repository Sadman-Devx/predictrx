from rest_framework import serializers
from rest_framework.exceptions import NotFound

from apps.analysis.models import AnalysisRun
from apps.patients.models import Patient

from .models import FollowUpTask


class FollowUpTaskSerializer(serializers.ModelSerializer):
    patient_id = serializers.IntegerField(read_only=True)
    patient_code = serializers.CharField(source="patient.patient_code", read_only=True)
    analysis_run_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = FollowUpTask
        fields = [
            "id",
            "patient_id",
            "patient_code",
            "analysis_run_id",
            "task_type",
            "status",
            "due_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class FollowUpTaskCreateSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(min_value=1)
    analysis_run_id = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    task_type = serializers.ChoiceField(choices=[value for value, _label in FollowUpTask.TASK_TYPES])
    due_date = serializers.DateField(allow_null=True, required=False)

    def validate(self, attrs):
        patient = Patient.objects.filter(pk=attrs.pop("patient_id"), owner=self.context["request"].user).first()
        if patient is None:
            raise NotFound()
        run_id = attrs.pop("analysis_run_id", None)
        run = None
        if run_id is not None:
            run = AnalysisRun.objects.filter(pk=run_id, patient=patient, status="completed").first()
            if run is None:
                raise serializers.ValidationError(
                    {"analysis_run_id": "Choose a completed analysis belonging to this patient."}
                )
        attrs["patient"] = patient
        attrs["analysis_run"] = run
        return attrs


class FollowUpTaskUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowUpTask
        fields = ["status", "due_date"]
