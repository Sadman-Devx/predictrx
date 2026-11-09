from .models import AuditLog

# Action names. Use these constants, never string literals, so a typo cannot create a silent audit gap.
PATIENT_LIST = "patient_list"
PATIENT_READ = "patient_read"
PATIENT_CREATE = "patient_create"
PATIENT_UPDATE = "patient_update"
ANALYSIS_START = "analysis_start"
FAMILY_VIEW = "family_view"
CONSENT_CHANGE = "consent_change"
IMAGE_ACCESS = "image_access"


def record(request, action: str, *, patient=None, obj=None, **meta) -> AuditLog:
    """Write an audit entry. Call this from every patient-data read, analysis start, family view, consent change.

    `meta` must never contain PII (names, phones, free text, field *values*). Field *names* and counts are fine.
    """
    ip = request.META.get("REMOTE_ADDR") if request is not None else None
    actor = getattr(request, "user", None)
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        object_type=obj.__class__.__name__ if obj is not None else "",
        object_id=str(getattr(obj, "pk", "")) if obj is not None else "",
        patient=patient,
        ip=ip,
        meta=meta,
    )