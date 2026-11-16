import ipaddress
import logging

from rest_framework.throttling import BaseThrottle

from .models import AuditLog

logger = logging.getLogger(__name__)

# Action names. Use these constants, never string literals, so a typo cannot create a silent audit gap.
PATIENT_LIST = "patient_list"
PATIENT_READ = "patient_read"
PATIENT_CREATE = "patient_create"
PATIENT_UPDATE = "patient_update"
MEDICATION_LIST = "medication_list"
MEDICATION_CREATE = "medication_create"
MEDICATION_UPDATE = "medication_update"
MEDICATION_DELETE = "medication_delete"
SCAN_UPLOAD = "scan_upload"
SCAN_READ = "scan_read"
ANALYSIS_START = "analysis_start"
ANALYSIS_READ = "analysis_read"
ANALYSIS_TRACE_READ = "analysis_trace_read"
PATIENT_CARD_READ = "patient_card_read"  # the plain-Bangla patient card of a run was read by its owner
TWIN_RUN = "twin_run"  # a what-if scenario was requested for a completed run (meta: replay, base_run_id, counts)
TWIN_READ = "twin_read"  # a stored what-if scenario (op=detail) or a run's scenario list (op=list) was read
FAMILY_VIEW = "family_view"  # a family user opened a patient's summary (or saw the patient in their list)
FAMILY_LINK = "family_link"  # a clinician listed / linked / re-linked / unlinked a family member (meta: op)
CONSENT_LIST = "consent_list"  # a clinician opened a patient's consent list
CONSENT_CHANGE = "consent_change"  # a consent was granted or revoked (meta: change, scope)
IMAGE_ACCESS = "image_access"  # a prescription image was streamed to its owner
IMAGE_DELETE = "image_delete"  # the owner deleted the image early
IMAGE_PURGE = "image_purge"  # retention deadline passed: the system deleted the image
EVAL_RUN = "eval_run"  # an admin started an evaluation run (no patient data involved)
BRAND_REVIEW = "brand_review"  # an admin verified / un-verified a brand mapping (meta: change, via, reason)
ADMIN_RECORD_READ = "admin_record_read"  # a staff user opened ONE patient-data record in the Django admin (meta: model)
ADMIN_LIST_READ = "admin_list_read"  # a staff user opened a list of patient-data records in the Django admin (meta: model)


def client_ip(request) -> str | None:
    """Real client IP, honouring REST_FRAMEWORK["NUM_PROXIES"] (same logic the throttles use).

    Returns None when there is no request or the value is not a valid IP: a malformed X-Forwarded-For header must
    never be able to make an audit write (and with it the whole request) fail.
    """
    if request is None or not hasattr(request, "META"):
        return None
    try:
        ident = BaseThrottle().get_ident(request)
        return str(ipaddress.ip_address((ident or "").strip()))
    except ValueError:
        return None


def record(request, action: str, *, patient=None, obj=None, **meta) -> AuditLog:
    """Write an audit entry. Call this from every patient-data read, analysis start, family view, consent change.

    `meta` must never contain PII (names, phones, free text, field *values*). Field *names* and counts are fine.
    """
    actor = getattr(request, "user", None)
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        object_type=obj.__class__.__name__ if obj is not None else "",
        object_id=str(getattr(obj, "pk", "")) if obj is not None else "",
        patient=patient,
        ip=client_ip(request),
        meta=meta,
    )