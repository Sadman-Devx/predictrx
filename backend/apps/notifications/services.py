from apps.analysis.models import AnalysisRun
from apps.clinical.models import PrescriptionScan

from .models import Notification


def record_scan_notification(scan: PrescriptionScan) -> Notification | None:
    event = {"extracted": "scan_ready", "failed": "scan_failed"}.get(scan.status)
    if event is None:
        return None
    notification, _ = Notification.objects.get_or_create(
        deduplication_key=f"scan:{scan.pk}:{event}",
        defaults={
            "recipient_id": scan.patient.owner_id,
            "event": event,
            "scan": scan,
        },
    )
    return notification


def record_analysis_notification(run: AnalysisRun) -> Notification | None:
    event = {"completed": "analysis_ready", "failed": "analysis_failed"}.get(run.status)
    if event is None:
        return None
    notification, _ = Notification.objects.get_or_create(
        deduplication_key=f"analysis:{run.pk}:{event}",
        defaults={
            "recipient_id": run.patient.owner_id,
            "event": event,
            "analysis_run": run,
        },
    )
    return notification
