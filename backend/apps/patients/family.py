"""Family (NRB) read side: what a linked family user may see, and the checks that gate it.

Rules enforced here (docs/rule.md §3):
  * A family user sees a patient ONLY through a FamilyLink that is switched on AND rests on a `family_view` consent that
    is still active. This is checked on EVERY request (not only when the link is created), so revoking the consent
    closes access immediately. A missing / foreign / revoked patient is a plain 404: existence is not leaked.
  * The summary is read-only and built from fixed templates + the frozen result of the latest COMPLETED analysis.
    It never contains dosing, strengths, frequencies, lab values, notes, or a "safe" claim, and it never says the
    doctor "is reviewing" anything (the system does not know that). Absence of a record is not safety.
  * Medicines are shown by generic name only, taken from the run's frozen `input_snapshot`, so the list always matches
    the alert it is shown with.
  * No N+1: the list is built with a fixed number of queries whatever the number of linked patients.
"""
from django.conf import settings
from rest_framework.exceptions import NotFound

from ai.guardrails.output_checks import DISCLAIMER_BN, DISCLAIMER_EN
from apps.analysis.models import AnalysisRun, RiskFinding

from .models import Consent, FamilyLink
from .services import FAMILY_SCOPE

SEVERITY_RANK = {"major": 0, "moderate": 1, "minor": 2, "unknown": 3}
NEEDS_REVIEW_LEVELS = ("major", "moderate")
MAX_PATIENTS_LISTED = 50

TALK_TO_DOCTOR_BN = "কোনো ওষুধ পরিবর্তন করার আগে অনুগ্রহ করে চিকিৎসকের সঙ্গে কথা বলুন।"
TALK_TO_DOCTOR_EN = "Please talk to your doctor before changing any medicine."

# level -> (Bangla, English). Fixed wording: no new medical fact can appear, and every text passes the output
# guardrail (no dosing, no un-negated "safe"). Clinical wording still needs the mentor/clinician sign-off (design.md §4.8).
ALERT_TEXT = {
    "major": (
        "কিছু ওষুধ একসাথে চললে বিশেষ নজর রাখা দরকার হতে পারে। এই বিষয়ে চিকিৎসকের সঙ্গে কথা বলুন।",
        "Some of the medicines may need special attention when used together. Please talk to the doctor about this.",
    ),
    "moderate": (
        "কিছু ওষুধের সংমিশ্রণে সতর্কতা আছে। এই বিষয়ে চিকিৎসকের সঙ্গে কথা বলুন।",
        "There is a caution about some of the medicine combinations. Please talk to the doctor about this.",
    ),
    "minor": (
        "কিছু ওষুধের সংমিশ্রণে সামান্য সতর্কতা আছে। চাইলে চিকিৎসকের সঙ্গে কথা বলে নিন।",
        "There is a minor caution about some of the medicine combinations. You may ask the doctor about it.",
    ),
    "unknown": (
        "এই তালিকার জন্য কোনো সতর্কতার রেকর্ড পাওয়া যায়নি। তবে রেকর্ড না থাকা মানে ওষুধগুলো একসাথে নিরাপদ, তা নয়।",
        "No interaction record was found for this list. This does not mean the combination is safe.",
    ),
    None: (
        "এখনো কোনো ওষুধ পর্যালোচনা সম্পন্ন হয়নি।",
        "No medication review has been completed yet.",
    ),
}


# ------------------------------------------------------------------------------------------------ access
def usable_links(user):
    """Links this family user may use right now: link on, `family_view` consent active, account active."""
    return FamilyLink.objects.filter(
        family_user=user,
        family_user__is_active=True,
        is_active=True,
        consent__scope=FAMILY_SCOPE,
        consent__revoked_at__isnull=True,
    ).select_related("patient", "consent")


def get_usable_link(user, patient_id: int) -> FamilyLink:
    """The link that lets `user` see `patient_id`, or a plain 404 (never a 403: existence is not leaked)."""
    link = usable_links(user).filter(patient_id=patient_id).first()
    if link is None:
        raise NotFound()
    return link


# ------------------------------------------------------------------------------------------------ latest analysis
def _latest_runs(patient_ids: list[int]) -> dict[int, AnalysisRun]:
    """Newest COMPLETED run per patient, in one query (PostgreSQL DISTINCT ON). A queued / running / failed run is never
    shown to a family member: a partial result must not look final."""
    if not patient_ids:
        return {}
    runs = (
        AnalysisRun.objects.filter(patient_id__in=patient_ids, status="completed")
        .order_by("patient_id", "-id")
        .distinct("patient_id")
    )
    return {run.patient_id: run for run in runs}


def _highest_severity(run_ids: list[int]) -> dict[int, str]:
    """run id -> its most severe finding (major > moderate > minor > unknown), in one query."""
    if not run_ids:
        return {}
    best: dict[int, str] = {}
    for run_id, severity in RiskFinding.objects.filter(run_id__in=run_ids).values_list("run_id", "severity"):
        severity = severity if severity in SEVERITY_RANK else "unknown"
        if run_id not in best or SEVERITY_RANK[severity] < SEVERITY_RANK[best[run_id]]:
            best[run_id] = severity
    return best


def _level_for(run: AnalysisRun | None, severities: dict[int, str]) -> str | None:
    """None = no completed analysis. A completed run with no finding rows counts as 'unknown' (no record found)."""
    if run is None:
        return None
    return severities.get(run.id, "unknown")


def _updated_at(run: AnalysisRun | None):
    return (run.finished_at or run.started_at) if run is not None else None


def _medicines(run: AnalysisRun | None) -> list[str]:
    """Generic names from the run's frozen snapshot, de-duplicated and sorted. Never strengths or frequencies."""
    if run is None:
        return []
    names = {
        str(m.get("generic_name")).strip()
        for m in (run.input_snapshot or {}).get("medications", [])
        if isinstance(m, dict) and m.get("generic_name")
    }
    return sorted(name for name in names if name)


def _consent_info(consent: Consent) -> dict:
    return {"scope": consent.scope, "granted_by": consent.granted_by, "granted_at": consent.granted_at}


# ------------------------------------------------------------------------------------------------ read models
def list_for_family(user) -> tuple[list[FamilyLink], list[dict]]:
    """(links, items) for GET /api/family/patients/. Three queries in total, whatever the number of patients."""
    links = list(usable_links(user).order_by("patient__patient_code")[:MAX_PATIENTS_LISTED])
    runs = _latest_runs([link.patient_id for link in links])
    severities = _highest_severity([run.id for run in runs.values()])

    items = []
    for link in links:
        run = runs.get(link.patient_id)
        level = _level_for(run, severities)
        items.append({
            "patient_id": link.patient_id,
            "patient_code": link.patient.patient_code,
            "relationship": link.relationship,
            "has_analysis": run is not None,
            "highest_severity": level,
            "needs_review": level in NEEDS_REVIEW_LEVELS,
            "last_updated": _updated_at(run),
            "consent": _consent_info(link.consent),
        })
    return links, items


def summary_for_family(link: FamilyLink) -> dict:
    """The read-only summary for one linked patient (GET /api/family/patients/{id}/summary/)."""
    patient = link.patient
    run = _latest_runs([patient.id]).get(patient.id)
    level = _level_for(run, _highest_severity([run.id]) if run is not None else {})
    message_bn, message_en = ALERT_TEXT[level]
    return {
        "patient_id": patient.id,
        "patient_code": patient.patient_code,
        "relationship": link.relationship,
        "read_only": True,
        "has_analysis": run is not None,
        "alert": {
            "level": level,
            "needs_review": level in NEEDS_REVIEW_LEVELS,
            "message_bn": message_bn,
            "message_en": message_en,
        },
        "talk_to_doctor_bn": TALK_TO_DOCTOR_BN,
        "talk_to_doctor_en": TALK_TO_DOCTOR_EN,
        "medicines": _medicines(run),
        "last_updated": _updated_at(run),
        "consent": _consent_info(link.consent),
        "disclaimer_version": settings.DISCLAIMER_VERSION,
        "disclaimer": {"version": settings.DISCLAIMER_VERSION, "text_en": DISCLAIMER_EN, "text_bn": DISCLAIMER_BN},
    }