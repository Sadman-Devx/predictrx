"""Executes one prescription scan inside a Celery worker (never inside a request/response cycle).

Life cycle:  queued --claim--> processing --store--> extracted
                                   \\--any failure--> failed (+ error_code)

* A duplicate delivery of the same task finds status != queued and returns 'skipped' (no second paid vision call).
* Consent is checked again here: it may have been revoked between upload and processing.
* Every failure ends in a clear `failed` state with a machine `error_code`; no partial draft is ever stored.
* Logs carry the scan id and the exception class only: never the image, the model reply or any extracted text.

error_code values: consent_revoked · image_missing · vision_not_configured · timeout · not_a_prescription ·
no_medications_found · invalid_model_output · extraction_failed · enqueue_failed (set by the API) · timeout (stuck sweep)
"""
import logging

from celery.exceptions import SoftTimeLimitExceeded

from ai.extraction import prescription
from ai.llm.router import LLMNotConfigured

from . import services
from .models import PrescriptionScan

logger = logging.getLogger(__name__)


def claim(scan_id: int) -> PrescriptionScan | None:
    """queued -> processing, atomically (a single UPDATE ... WHERE status='queued')."""
    if not PrescriptionScan.objects.filter(pk=scan_id, status="queued").update(status="processing"):
        return None
    return PrescriptionScan.objects.select_related("patient").get(pk=scan_id)


def fail(scan_id: int, code: str) -> None:
    """Never overwrites a scan that already finished as `extracted`."""
    PrescriptionScan.objects.filter(pk=scan_id).exclude(status="extracted").update(status="failed", error_code=code)


def execute_scan(scan_id: int) -> str:
    """Run one extraction end to end. Returns the final status, or 'skipped' if another worker already took it."""
    scan = claim(scan_id)
    if scan is None:
        return "skipped"
    try:
        if not services.has_active_consent(scan.patient_id, "analysis"):
            fail(scan_id, "consent_revoked")
            return "failed"
        if not scan.image:
            fail(scan_id, "image_missing")
            return "failed"
        with scan.image.open("rb") as handle:
            data = handle.read()
        result = prescription.extract_from_image(data, scan.content_type or "image/jpeg")
        if not services.store_extraction(scan, result):
            return "skipped"  # the scan was failed by the stuck-scan sweeper while the model was working
        return "extracted"
    except SoftTimeLimitExceeded:
        fail(scan_id, "timeout")
    except FileNotFoundError:
        fail(scan_id, "image_missing")
    except LLMNotConfigured:
        logger.error("scan %s: no vision model is configured in this worker", scan_id)
        fail(scan_id, "vision_not_configured")
    except prescription.ExtractionError as exc:
        fail(scan_id, exc.code)
    except Exception as exc:  # noqa: BLE001 — last resort: a crashed scan must end in a clear failed state
        logger.exception("scan %s failed (%s)", scan_id, exc.__class__.__name__)
        fail(scan_id, "extraction_failed")
    return "failed"