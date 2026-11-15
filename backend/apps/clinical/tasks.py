"""Celery tasks for prescription scans. All logic lives in runner.py / services.py (tasks stay thin)."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.audit import services as audit

from . import runner, services
from .models import PrescriptionScan

logger = logging.getLogger(__name__)


@shared_task(soft_time_limit=200)  # below CELERY_TASK_TIME_LIMIT (300 s) so the runner can still mark the scan `failed`
def extract_prescription(scan_id: int) -> str:
    """Vision model -> draft Medication rows (always unconfirmed). See runner.execute_scan."""
    return runner.execute_scan(scan_id)


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
    """A scan still queued/processing after SCAN_STUCK_MINUTES lost its worker (crash, broker restart): fail it visibly."""
    cutoff = timezone.now() - timedelta(minutes=settings.SCAN_STUCK_MINUTES)
    stuck = PrescriptionScan.objects.filter(status__in=["queued", "processing"], created_at__lt=cutoff)
    n = stuck.update(status="failed", error_code="timeout")
    if n:
        logger.warning("marked %s stuck prescription scan(s) as failed", n)
    return n