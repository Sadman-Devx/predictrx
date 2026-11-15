from django.db import transaction
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from core.permissions import IsDoctorOrPharmacist

from . import services
from .serializers import (DraftMedicationSerializer, MedicationUpdateSerializer, ScanDetailSerializer,
                          ScanUploadResponseSerializer, ScanUploadSerializer)


class ScanUploadView(APIView):
    """POST /api/prescriptions/scan/ — upload a prescription photo. Returns at once with a scan id; OCR runs in Celery.

    202 = new scan queued · 200 = the same image was just uploaded for this patient (existing scan returned).
    Needs the patient's active `analysis` consent (403 `consent_required`). JPEG / PNG / WebP only, size-capped.
    """

    permission_classes = [IsDoctorOrPharmacist]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "scan"

    @extend_schema(
        tags=["Prescriptions"],
        request={"multipart/form-data": ScanUploadSerializer},
        responses={202: ScanUploadResponseSerializer, 200: ScanUploadResponseSerializer},
    )
    def post(self, request):
        ser = ScanUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            scan, created = services.create_scan(request, **ser.validated_data)
        body = {
            "scan_id": scan.id,
            "status": scan.status,
            "idempotent_replay": not created,
            "retain_until": scan.retain_until,
        }
        return Response(body, status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK)


class ScanDetailView(APIView):
    """GET /api/prescriptions/scan/{id}/ — poll the status; read the DRAFT medication list once `extracted`.
    DELETE /api/prescriptions/scan/{id}/ — delete the image file now (the draft rows stay).

    * queued / processing / failed: status only (`error_code` says why a scan failed). `drafts` is null.
    * extracted: draft rows with resolver hints. Reading them returns patient-related content, so it is audited.
    * Status polls carry no clinical content and are NOT audited (a 2-second poll would flood the log).
    """

    permission_classes = [IsDoctorOrPharmacist]
    throttle_scope = "scan_poll"

    @extend_schema(tags=["Prescriptions"], responses=ScanDetailSerializer)
    def get(self, request, pk):
        scan = services.get_owned_scan(request.user, pk)
        if scan.status != "extracted":
            return Response(ScanDetailSerializer(scan).data)

        drafts = list(scan.medications.select_related("drug").order_by("id"))
        audit.record(request, audit.SCAN_READ, patient=scan.patient, obj=scan, drafts=len(drafts))
        context = {"drafts": drafts, "hints": services.draft_hints(scan)}
        return Response(ScanDetailSerializer(scan, context=context).data)

    @extend_schema(tags=["Prescriptions"], responses={204: OpenApiResponse(description="Image deleted (or already gone)")})
    @transaction.atomic
    def delete(self, request, pk):
        scan = services.get_owned_scan(request.user, pk)
        if scan.status == "processing":
            raise services.ScanRequestError("scan_in_progress", "The scan is being processed. Try again in a moment.",
                                            http_status=status.HTTP_409_CONFLICT)
        if services.delete_scan_image(scan):
            audit.record(request, audit.IMAGE_DELETE, patient=scan.patient, obj=scan)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ScanImageView(APIView):
    """GET /api/prescriptions/scan/{id}/image/ — the stored image, for the Review screen (image next to the list).

    The only way an image leaves the server: JWT required, owner only (foreign id = 404), audited (`image_access`),
    never cached by the browser or a proxy. The frontend must fetch it with the Authorization header and show it from a
    blob (an <img src> cannot send a token, and there is deliberately no public URL).
    """

    permission_classes = [IsDoctorOrPharmacist]
    throttle_scope = "scan_poll"

    @extend_schema(
        tags=["Prescriptions"],
        responses={(200, "image/jpeg"): OpenApiTypes.BINARY, (200, "image/png"): OpenApiTypes.BINARY,
                   (200, "image/webp"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        scan = services.get_owned_scan(request.user, pk)
        if not scan.image:
            raise NotFound()  # purged or deleted: the draft list is still available from the detail endpoint
        try:
            handle = scan.image.open("rb")
        except FileNotFoundError as exc:
            raise NotFound() from exc
        audit.record(request, audit.IMAGE_ACCESS, patient=scan.patient, obj=scan)
        response = FileResponse(handle, content_type=scan.content_type or "application/octet-stream")
        response["Cache-Control"] = "private, no-store"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class MedicationDetailView(APIView):
    """PATCH /api/medications/{id}/ — edit / confirm one medication (Review & Confirm).
    DELETE /api/medications/{id}/ — remove a row (409 if an analysis run was built from it).

    Owner only (foreign id = 404). Every change is audited with field NAMES only, never values.
    """

    permission_classes = [IsDoctorOrPharmacist]

    @extend_schema(tags=["Medications"], request=MedicationUpdateSerializer, responses=DraftMedicationSerializer)
    @transaction.atomic
    def patch(self, request, pk):
        med = services.get_owned_medication(request.user, pk)
        ser = MedicationUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        changed = services.update_medication(med, ser.validated_data)
        audit.record(request, audit.MEDICATION_UPDATE, patient=med.patient, obj=med, fields=changed,
                     confirmed=med.confirmed_by_user)
        return Response(DraftMedicationSerializer(med).data)

    @extend_schema(tags=["Medications"], responses={204: OpenApiResponse(description="Deleted")})
    @transaction.atomic
    def delete(self, request, pk):
        med = services.get_owned_medication(request.user, pk)
        if services.medication_in_analysis(med):
            raise services.ScanRequestError(
                "medication_in_analysis",
                "This medication was used in an analysis run and cannot be deleted.",
                http_status=status.HTTP_409_CONFLICT,
            )
        audit.record(request, audit.MEDICATION_DELETE, patient=med.patient, obj=med)  # before delete: the id is still known
        med.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)