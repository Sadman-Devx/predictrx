"""Prescription scan + medication-draft services (business logic; views stay thin).

Rules enforced here (docs/rule.md):
  * Ownership is derived from the authenticated user. A foreign or missing patient / scan / medication is a plain 404.
  * An image reaches a vision model only after the patient's `analysis` consent (backend-design §6.4).
  * The file type is decided from the file's own bytes, never from the client's filename or Content-Type.
  * Images are private and short-lived: `retain_until` is set at upload; the purge task and the owner can delete early.
  * Human in the loop: scan output is ALWAYS a draft (`confirmed_by_user=False`). A drug is attached automatically only
    for an exact brand/generic match; a typo-level (fuzzy) or ambiguous match stays `unresolved` and is shown as a hint.
  * Editing the name of a row removes its drug link: a link made for "Napa" must never silently survive a rename.
  * A medication that an analysis run was built from cannot be deleted (PROTECT intent in rule.md §4).
"""
import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from apps.audit import services as audit
from apps.drugs import services as drug_services
from apps.drugs.models import Drug
from apps.patients.models import Consent, Patient

from .models import Medication, PrescriptionScan

logger = logging.getLogger(__name__)

# Only image formats every vision model accepts. Decided by magic bytes.
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
AUTO_RESOLVE_MATCH_TYPES = {"exact", "generic"}  # a fuzzy match is a hint for the user, never an automatic link
CONTENT_FIELDS = ("raw_text", "brand_name", "strength", "frequency")
NAME_FIELDS = ("raw_text", "brand_name")
HINT_KEYS = ("status", "generic", "confidence", "match_type", "verified", "reason", "candidates")
EXTRACTION_VERSION = 1


class ScanRequestError(APIException):
    """Client-fixable problem. Shape: {"error": {"code": <specific>, "message": ..., "details": {"detail", "code", ...}}}."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"

    def __init__(self, code: str, message: str, *, http_status: int | None = None, **extra):
        super().__init__(detail={"detail": message, "code": code, **extra})
        if http_status:
            self.status_code = http_status


# ------------------------------------------------------------------------------------------------ helpers
def sniff_image_type(head: bytes) -> str | None:
    """Image type from the first bytes of the file. Anything else (PDF, HTML, SVG, executable...) -> None."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def has_active_consent(patient_id: int, scope: str) -> bool:
    return Consent.objects.filter(patient_id=patient_id, scope=scope, revoked_at__isnull=True).exists()


def retention_deadline(patient_id: int):
    """Short by default; the longer window applies only while an active `retain_images` consent exists."""
    days = settings.PRESCRIPTION_IMAGE_RETENTION_DAYS
    if has_active_consent(patient_id, "retain_images"):
        days = settings.PRESCRIPTION_IMAGE_RETAINED_DAYS
    return timezone.now() + timedelta(days=days)


def get_owned_scan(user, pk: int) -> PrescriptionScan:
    scan = PrescriptionScan.objects.select_related("patient").filter(pk=pk, patient__owner=user).first()
    if scan is None:
        raise NotFound()
    return scan


def get_owned_medication(user, pk: int) -> Medication:
    med = Medication.objects.select_related("drug", "patient").filter(pk=pk, patient__owner=user).first()
    if med is None:
        raise NotFound()
    return med


# ------------------------------------------------------------------------------------------------ upload
def _enqueue(scan_id: int) -> None:
    """Called after the transaction commits, so the worker can never see a scan that does not exist yet."""
    from .tasks import extract_prescription

    try:
        extract_prescription.delay(scan_id)
    except Exception:  # noqa: BLE001 — broker outage (Redis down): fail visibly instead of leaving a scan 'queued' forever
        logger.exception("could not enqueue prescription scan %s", scan_id)
        PrescriptionScan.objects.filter(pk=scan_id, status="queued").update(status="failed", error_code="enqueue_failed")


def create_scan(request, *, patient_id: int, image) -> tuple[PrescriptionScan, bool]:
    """Store the image privately and queue extraction. Returns (scan, created). Call inside `transaction.atomic()`.

    The same image re-sent for the same patient within SCAN_DEDUPE_WINDOW_SECONDS returns the existing scan
    (a double click must not start two paid vision calls). A failed scan is never reused: uploading again retries.
    """
    user = request.user
    patient = Patient.objects.filter(pk=patient_id, owner=user).first()
    if patient is None:
        raise NotFound()  # 404, not 403: existence of other doctors' patients is not leaked

    if not has_active_consent(patient.id, "analysis"):
        raise ScanRequestError(
            "consent_required",
            "The patient's consent for analysis is required before a prescription image can be processed.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    if image.size > settings.SCAN_MAX_UPLOAD_BYTES:
        raise ScanRequestError("file_too_large", "The image is too large.", http_status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                               max_bytes=settings.SCAN_MAX_UPLOAD_BYTES)
    data = image.read()
    if not data:
        raise ScanRequestError("empty_file", "The uploaded file is empty.")
    content_type = sniff_image_type(data[:16])
    if content_type is None:
        raise ScanRequestError("unsupported_image_type", "Upload a JPEG, PNG or WebP image.",
                               http_status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, allowed=sorted(IMAGE_TYPES))

    digest = hashlib.sha256(data).hexdigest()
    since = timezone.now() - timedelta(seconds=settings.SCAN_DEDUPE_WINDOW_SECONDS)
    existing = (
        PrescriptionScan.objects.filter(patient=patient, image_sha256=digest, created_at__gte=since)
        .exclude(status="failed")
        .exclude(image="")
        .order_by("-id")
        .first()
    )
    if existing is not None:
        audit.record(request, audit.SCAN_UPLOAD, patient=patient, obj=existing, replay=True, bytes=len(data))
        return existing, False

    scan = PrescriptionScan(patient=patient, content_type=content_type, image_sha256=digest,
                            retain_until=retention_deadline(patient.id))
    scan.image.save("scan", ContentFile(data), save=False)  # the real name is random: see models.scan_upload_path
    try:
        scan.save()
        audit.record(request, audit.SCAN_UPLOAD, patient=patient, obj=scan, replay=False, bytes=len(data),
                     content_type=content_type)
    except Exception:
        scan.image.delete(save=False)  # never leave an orphan image on disk when the database write failed
        raise
    transaction.on_commit(lambda: _enqueue(scan.id))
    return scan, True


# ------------------------------------------------------------------------------------------------ image lifecycle
def delete_scan_image(scan: PrescriptionScan) -> bool:
    """Remove the image file but keep the row and its draft list. Returns True if a file was removed."""
    if not scan.image:
        return False
    scan.image.delete(save=False)
    scan.image = ""
    scan.image_deleted_at = timezone.now()
    scan.save(update_fields=["image", "image_deleted_at"])
    return True


# ------------------------------------------------------------------------------------------------ extraction result
def _hint(resolution: dict) -> dict:
    return {k: resolution[k] for k in HINT_KEYS if k in resolution}


@transaction.atomic
def store_extraction(scan: PrescriptionScan, result) -> list[Medication]:
    """Turn a validated extraction into draft Medication rows and mark the scan `extracted`.

    Returns [] (and changes nothing) if the scan is no longer `processing` (e.g. the stuck-scan sweeper failed it).
    """
    locked = PrescriptionScan.objects.select_for_update().get(pk=scan.pk)
    if locked.status != "processing":
        return []

    resolutions = [
        drug_services.resolve_brand(d["brand_name"] or d["raw_text"], d["strength"] or None) for d in result.drafts
    ]
    generics = {
        r["generic"] for r in resolutions
        if r.get("status") == "resolved" and r.get("match_type") in AUTO_RESOLVE_MATCH_TYPES
    }
    drugs = {d.generic_name: d for d in Drug.objects.filter(generic_name__in=generics)} if generics else {}

    rows = []
    for draft, resolution in zip(result.drafts, resolutions):
        drug = drugs.get(resolution.get("generic")) if resolution.get("match_type") in AUTO_RESOLVE_MATCH_TYPES else None
        rows.append(Medication(
            patient_id=locked.patient_id, scan=locked, raw_text=draft["raw_text"], brand_name=draft["brand_name"],
            strength=draft["strength"], frequency=draft["frequency"], drug=drug,
            resolution_status="resolved" if drug else "unresolved",
            confirmed_by_user=False,  # always: a person must confirm every scanned row
            source="scan",
        ))
    meds = Medication.objects.bulk_create(rows)

    locked.extracted_json = {
        "version": EXTRACTION_VERSION,
        "legibility": result.legibility,
        "truncated": result.truncated,
        "redactions": result.redactions,
        "model": {"provider": result.provider, "name": result.model},
        "drafts": [{"medication_id": m.id, "resolution": _hint(r)} for m, r in zip(meds, resolutions)],
    }
    locked.status = "extracted"
    locked.error_code = ""
    locked.save(update_fields=["extracted_json", "status", "error_code"])
    return meds


def draft_hints(scan: PrescriptionScan) -> dict[int, dict]:
    """medication_id -> resolver hint (basis of the auto-resolution, or candidates for an unresolved row)."""
    drafts = (scan.extracted_json or {}).get("drafts") or []
    return {d["medication_id"]: d.get("resolution") or {} for d in drafts if isinstance(d, dict) and "medication_id" in d}


# ------------------------------------------------------------------------------------------------ medication edit / confirm
def update_medication(med: Medication, data: dict) -> list[str]:
    """Apply an edit/confirm from the Review screen. Returns the NAMES of the fields that changed (never values: PII-adjacent).

    data may hold: raw_text, brand_name, strength, frequency, drug (a Drug or None), confirmed_by_user (bool).
    """
    changed = []
    for name in CONTENT_FIELDS:
        if name in data and getattr(med, name) != data[name]:
            setattr(med, name, data[name])
            changed.append(name)

    drug_given = "drug" in data
    if drug_given and data["drug"] != med.drug:
        med.drug = data["drug"]
        changed.append("drug")
    elif not drug_given and any(n in changed for n in NAME_FIELDS):
        # The name changed but no drug was chosen: the old link no longer describes this row. Ask again, never keep it.
        if med.drug_id is not None:
            med.drug = None
            changed.append("drug")

    confirm = data.get("confirmed_by_user")
    if confirm is True:
        med.confirmed_by_user = True
    elif changed or confirm is False:
        med.confirmed_by_user = False  # an edit invalidates the earlier confirmation

    drug_chosen_now = drug_given and "drug" in changed and med.drug_id is not None
    if med.drug_id is None:
        med.resolution_status = "unresolved"
    elif drug_chosen_now or med.confirmed_by_user:
        med.resolution_status = "user_confirmed"  # a person picked or confirmed the drug
    else:
        med.resolution_status = "resolved"

    update_fields = list(dict.fromkeys([*changed, "confirmed_by_user", "resolution_status"]))
    med.save(update_fields=update_fields)
    return sorted(set(changed))


def medication_in_analysis(med: Medication) -> bool:
    """True if any analysis run was built from this medication (its id is frozen in the run's input snapshot)."""
    from apps.analysis.models import AnalysisRun

    return AnalysisRun.objects.filter(patient_id=med.patient_id, input_snapshot__medication_ids__contains=[med.id]).exists()