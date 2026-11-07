from celery import shared_task
from django.utils import timezone

from .models import PrescriptionScan


@shared_task
def purge_expired_scans() -> int:
    """Delete prescription image files whose retention deadline passed. Keeps the DB row, drops the file."""
    n = 0
    for scan in PrescriptionScan.objects.filter(retain_until__lt=timezone.now()).exclude(image=""):
        scan.image.delete(save=False)
        scan.image = ""
        scan.save(update_fields=["image"])
        n += 1
    return n


# TODO (lead + backend): extract_prescription(scan_id) — vision model -> draft Medication rows.
