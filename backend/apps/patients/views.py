from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.clinical.models import Medication
from core.permissions import IsDoctorOrPharmacist, IsPatientOwner

from . import consent_banner, invites, services
from .models import Patient
from .serializers import (
    ConsentBannerSerializer,
    ConsentCreateSerializer,
    ConsentListSerializer,
    ConsentRevokeResponseSerializer,
    ConsentSerializer,
    FamilyLinkCreatedSerializer,
    FamilyLinkCreateSerializer,
    FamilyLinkListSerializer,
    FamilyLinkSerializer,
    MedicationSerializer,
    PatientAnalysisHistorySerializer,
    PatientSerializer,
)
from apps.analysis.models import AnalysisRun


def envelope(items) -> dict:
    """Same list shape as the paginated endpoints ({count, next, previous, results}) so the frontend reuses one type."""
    items = list(items)
    return {"count": len(items), "next": None, "previous": None, "results": items}


class PatientViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    /api/patients/  (GET list, POST create)  ·  /api/patients/{id}/  (GET, PATCH)

    - Only doctors/pharmacists; each sees only the patients they own (a foreign id is a 404, not a 403,
      so existence is not leaked).
    - Every read/create/update writes an AuditLog row in the same transaction. If the audit write fails,
      the request fails: no patient data is returned without a trail.
    - No DELETE and no PUT by design (Patient is PROTECT-referenced by analysis runs).
    - Each patient also carries `consent_active` (active `analysis` consent), `active_consent_scopes` and
      `medication_count`, computed by the server (the list is loaded without N+1 queries).
    """

    serializer_class = PatientSerializer
    permission_classes = [IsDoctorOrPharmacist, IsPatientOwner]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # drf-spectacular schema generation has no real user
            return Patient.objects.none()
        return services.patients_for(self.request.user)

    @transaction.atomic
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        audit.record(request, audit.PATIENT_LIST, count=len(response.data["results"]))
        return response

    @transaction.atomic
    def retrieve(self, request, *args, **kwargs):
        patient = self.get_object()
        audit.record(request, audit.PATIENT_READ, patient=patient, obj=patient)
        return Response(self.get_serializer(patient).data)

    @action(detail=True, methods=["get"], url_path="analysis-history")
    @extend_schema(responses=PatientAnalysisHistorySerializer)
    @transaction.atomic
    def analysis_history(self, request, *args, **kwargs):
        patient = self.get_object()
        runs = AnalysisRun.objects.filter(patient=patient, status="completed").annotate(
            occurred_at=Coalesce("finished_at", "started_at"),
            findings_count=Count("findings"),
            major_count=Count("findings", filter=Q(findings__severity="major")),
            moderate_count=Count("findings", filter=Q(findings__severity="moderate")),
            minor_count=Count("findings", filter=Q(findings__severity="minor")),
            unknown_count=Count("findings", filter=Q(findings__severity="unknown")),
            verified_count=Count("findings", filter=Q(findings__verification_status="verified")),
            unverified_count=Count("findings", filter=Q(findings__verification_status="unverified")),
            conflict_count=Count("findings", filter=Q(findings__verification_status="conflict")),
        )
        total_count = runs.count()
        latest_runs = list(runs.order_by("-occurred_at", "-pk")[:12])
        latest_runs.reverse()

        results = [
            {
                "run_id": run.pk,
                "occurred_at": run.occurred_at,
                "medication_count": len((run.input_snapshot or {}).get("medication_ids") or []),
                "findings_count": run.findings_count,
                "severity_counts": {
                    "major": run.major_count,
                    "moderate": run.moderate_count,
                    "minor": run.minor_count,
                    "unknown": run.unknown_count,
                },
                "verification_counts": {
                    "verified": run.verified_count,
                    "unverified": run.unverified_count,
                    "conflict": run.conflict_count,
                },
            }
            for run in latest_runs
        ]
        body = PatientAnalysisHistorySerializer({"total_count": total_count, "results": results}).data
        audit.record(request, audit.PATIENT_ANALYSIS_HISTORY_READ, patient=patient, obj=patient,
                     analyses=len(results))
        return Response(body)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient = services.create_patient(owner=request.user, data=serializer.validated_data)
        audit.record(request, audit.PATIENT_CREATE, patient=patient, obj=patient)
        return Response(self.get_serializer(patient).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        patient = self.get_object()
        serializer = self.get_serializer(patient, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changed = services.update_patient(patient, serializer.validated_data)
        audit.record(request, audit.PATIENT_UPDATE, patient=patient, obj=patient, fields=changed)
        return Response(self.get_serializer(patient).data)


# Re-exported for backwards compatibility: the constants now live in apps/audit/services.py with every other action.
MEDICATION_LIST = audit.MEDICATION_LIST
MEDICATION_CREATE = audit.MEDICATION_CREATE


class MedicationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    /api/patients/{patient_pk}/medications/  (GET list, POST create)

    Nested under a patient. Only the patient's owner (doctor/pharmacist) can access; a foreign or missing patient
    is a plain 404 (existence is not leaked, and it is never a 500). Every read/write is audit-logged.
    Edit / confirm / delete of ONE medication lives in apps/clinical (PATCH/DELETE /api/medications/{id}/).
    """

    serializer_class = MedicationSerializer
    permission_classes = [IsDoctorOrPharmacist]
    http_method_names = ["get", "post", "head", "options"]

    def _get_patient(self) -> Patient:
        """Parent patient, fetched ONCE per request and only if the caller owns it (ownership comes from the token)."""
        if not hasattr(self, "_patient_cache"):
            patient = Patient.objects.filter(pk=self.kwargs["patient_pk"], owner=self.request.user).first()
            if patient is None:
                raise NotFound()
            self._patient_cache = patient
        return self._patient_cache

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Medication.objects.none()
        return services.list_medications(self._get_patient())

    @transaction.atomic
    def list(self, request, *args, **kwargs):
        patient = self._get_patient()
        response = super().list(request, *args, **kwargs)
        data = response.data
        count = len(data["results"]) if isinstance(data, dict) and "results" in data else len(data)
        audit.record(request, audit.MEDICATION_LIST, patient=patient, count=count)
        return response

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        patient = self._get_patient()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        medication = services.add_medication(patient, serializer.validated_data)
        audit.record(request, audit.MEDICATION_CREATE, patient=patient, obj=medication)
        return Response(self.get_serializer(medication).data, status=status.HTTP_201_CREATED)


# ------------------------------------------------------------------------------------------------ consent
class ConsentListCreateView(APIView):
    """/api/patients/{patient_pk}/consents/  (GET history, POST grant)

    Owner only (doctor / pharmacist); a foreign or missing patient is a 404. Granting records the scope and who gave
    the consent; the time is the server clock. A second active consent for the same scope is a 409
    `consent_already_active`. Every call is audited (`consent_list` / `consent_change`).
    """

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Consent"], responses=ConsentListSerializer)
    def get(self, request, patient_pk):
        with transaction.atomic():
            patient = services.get_owned_patient(request.user, patient_pk)
            consents = list(services.list_consents(patient))
            audit.record(request, audit.CONSENT_LIST, patient=patient, count=len(consents))
        return Response(envelope(ConsentSerializer(consents, many=True).data))

    @extend_schema(tags=["Consent"], request=ConsentCreateSerializer, responses={201: ConsentSerializer})
    def post(self, request, patient_pk):
        with transaction.atomic():
            patient = services.get_owned_patient(request.user, patient_pk, lock=True)
            serializer = ConsentCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            consent = services.grant_consent(patient, **serializer.validated_data)
            audit.record(request, audit.CONSENT_CHANGE, patient=patient, obj=consent, change="granted",
                         scope=consent.scope)
        return Response(ConsentSerializer(consent).data, status=status.HTTP_201_CREATED)


class ConsentRevokeView(APIView):
    """POST /api/patients/{patient_pk}/consents/{id}/revoke/

    Revoking never deletes: the row stays as history. It also switches off what rested on it: family links (for
    `family_view`) and long image retention (for `retain_images`); the response says how many. Revoking an already
    revoked consent is harmless (200, nothing changes, no second audit entry).
    """

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Consent"], request=None, responses={200: ConsentRevokeResponseSerializer})
    def post(self, request, patient_pk, pk):
        with transaction.atomic():
            patient = services.get_owned_patient(request.user, patient_pk, lock=True)
            consent, effects = services.revoke_consent(patient, pk)
            if effects is not None:
                audit.record(request, audit.CONSENT_CHANGE, patient=patient, obj=consent, change="revoked",
                             scope=consent.scope, **effects)
        effects = effects or {"family_links_deactivated": 0, "images_retention_shortened": 0}
        return Response({"consent": ConsentSerializer(consent).data, **effects})


class ConsentBannerView(APIView):
    """GET /api/patients/{patient_pk}/consent-banner/

    What the ConsentBanner shows for this patient: per-scope state (active / revoked / missing), whether anything is
    blocked (a prescription scan needs an active `analysis` consent), the next action, family access and image
    retention. Read-only: granting and revoking stay in the consent endpoints. Owner only; a foreign or missing
    patient is a 404. Audited as `consent_list` (meta: view=banner). Never cached.
    """

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Consent"], responses=ConsentBannerSerializer)
    def get(self, request, patient_pk):
        with transaction.atomic():
            patient = services.get_owned_patient(request.user, patient_pk)
            body = consent_banner.consent_banner(patient)
            audit.record(request, audit.CONSENT_LIST, patient=patient, view="banner", count=len(body["scopes"]))
        response = Response(ConsentBannerSerializer(body).data)
        response["Cache-Control"] = "no-store"
        return response


# ------------------------------------------------------------------------------------------------ family links
class FamilyInviteThrottle(UserRateThrottle):
    """Linking can create an account and send an e-mail: cap it per clinician (in addition to the global ceiling)."""

    scope = "family_invite"
    rate = "20/hour"


class FamilyLinkListCreateView(APIView):
    """/api/patients/{patient_pk}/family/  (GET links, POST link a family member)

    Owner only. Linking needs an active `family_view` consent (403 `family_consent_required`). Only `family`-role
    accounts can be linked: an unknown e-mail gets a new invited account (`invited: true`) and an invitation e-mail
    with no patient information in it. Every call is audited (`family_link`).
    """

    permission_classes = [IsDoctorOrPharmacist]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method == "POST":
            throttles.append(FamilyInviteThrottle())
        return throttles

    @extend_schema(tags=["Family"], responses=FamilyLinkListSerializer)
    def get(self, request, patient_pk):
        with transaction.atomic():
            patient = services.get_owned_patient(request.user, patient_pk)
            links = list(services.list_family_links(patient))
            audit.record(request, audit.FAMILY_LINK, patient=patient, op="list", count=len(links))
        return Response(envelope(FamilyLinkSerializer(links, many=True).data))

    @extend_schema(tags=["Family"], request=FamilyLinkCreateSerializer, responses={201: FamilyLinkCreatedSerializer})
    def post(self, request, patient_pk):
        with transaction.atomic():
            patient = services.get_owned_patient(request.user, patient_pk, lock=True)
            serializer = FamilyLinkCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            link, invited = services.link_family_member(
                patient,
                email=data["email"],
                relationship=data["relationship"],
                display_name=data.get("display_name", ""),
                consent_id=data.get("consent_id"),
            )
            audit.record(request, audit.FAMILY_LINK, patient=patient, obj=link, op="link", invited=invited,
                         family_user_id=link.family_user_id, consent_id=link.consent_id)
            if invited:  # only after the commit: the mail must never go out for a link that was rolled back
                family_user = link.family_user
                transaction.on_commit(lambda: invites.send_family_invite(family_user))
        link.invited = invited
        return Response(FamilyLinkCreatedSerializer(link).data, status=status.HTTP_201_CREATED)


class FamilyLinkDetailView(APIView):
    """DELETE /api/patients/{patient_pk}/family/{id}/ — switch a family member's access off.

    The link row stays (who had access, and when, is history); the audit log records the change. Idempotent.
    """

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Family"], request=None, responses={204: OpenApiResponse(description="Access switched off")})
    def delete(self, request, patient_pk, pk):
        with transaction.atomic():
            patient = services.get_owned_patient(request.user, patient_pk, lock=True)
            link = services.unlink_family_member(patient, pk)
            audit.record(request, audit.FAMILY_LINK, patient=patient, obj=link, op="unlink",
                         family_user_id=link.family_user_id)
        return Response(status=status.HTTP_204_NO_CONTENT)