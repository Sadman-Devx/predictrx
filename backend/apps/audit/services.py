from .models import AuditLog


def record(request, action: str, *, patient=None, obj=None, **meta) -> AuditLog:
    """Write an audit entry. Call this from every patient-data read, analysis start, family view, consent change."""
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
