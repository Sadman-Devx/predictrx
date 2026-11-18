"""Celery tasks for prescription scans. All logic lives in runner.py / services.py (tasks stay thin)."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.audit import services as audit
from apps.notifications.services import record_scan_notification

from . import runner, services
from .models import PrescriptionScan

logger = logging.getLogger(__name__)


@shared_task(soft_time_limit=200)  # below CELERY_TASK_TIME_LIMIT (300 s) so the runner can still mark the scan `failed`
def extract_prescription(scan_id: int) -> str:
    """Vision model -> draft Medication rows (always unconfirmed), then notify the owner of the final status."""
    result = runner.execute_scan(scan_id)
    scan = PrescriptionScan.objects.select_related("patient").filter(pk=scan_id).first()
    if scan is not None:
        record_scan_notification(scan)
    return result


@shared_task
def purge_expired_scans() -> int:
    """Delete prescription image FILES whose retention deadline passed. Keeps the row and its draft list.

    Skips scans that are being processed right now (the worker is reading the file); the next hourly run gets them.
    Every purge is audited (the trail survives, the image does not).
    """
    purged = 0
    expired = (
        PrescriptionScan.objects.filter(retain_until__lt=timezone.now())
        .exclude(image="")
        .exclude(status="processing")
        .select_related("patient")
    )
    for scan in expired.iterator():
        if services.delete_scan_image(scan):
            audit.record(None, audit.IMAGE_PURGE, patient=scan.patient, obj=scan, reason="retention")
            purged += 1
    return purged


@shared_task
def fail_stuck_scans() -> int:
    """Fail and notify scans still queued/processing after SCAN_STUCK_MINUTES (crash, broker restart)."""
    cutoff = timezone.now() - timedelta(minutes=settings.SCAN_STUCK_MINUTES)
    stuck = PrescriptionScan.objects.filter(status__in=["queued", "processing"], created_at__lt=cutoff)
    stuck_ids = list(stuck.values_list("pk", flat=True))
    n = stuck.update(status="failed", error_code="timeout")
    if n:
        failed_scans = (
            PrescriptionScan.objects.filter(pk__in=stuck_ids, status="failed", error_code="timeout")
            .select_related("patient")
        )
        for scan in failed_scans:
            record_scan_notification(scan)
        logger.warning("marked %s stuck prescription scan(s) as failed", n)
    return n