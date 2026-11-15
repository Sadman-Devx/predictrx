"""Consent banner: what the UI's ConsentBanner shows for ONE patient (design.md §1.2 / §4.6).

The server decides; the UI only renders. Rules:
  * Read-only. Granting and revoking stay in `services.py` (single place for those rules).
  * Honest states: `missing` (never recorded) and `revoked` (withdrawn) are different, and the wording differs.
  * `blocks` lists only what the server really refuses today: a prescription scan needs an ACTIVE `analysis`
    consent (apps/clinical/services.py). The banner never promises or denies anything the server does not enforce.
  * Fixed Bangla + English wording: no names, no medical claims, no dosing. Bangla clinical/consent wording still
    needs the mentor/clinician review (design.md §4.8).
  * Fixed number of queries (3), whatever the history of the patient.
"""
from django.conf import settings

from apps.clinical.models import PrescriptionScan

from .models import Patient
from .services import ANALYSIS_SCOPE, FAMILY_SCOPE, RETAIN_IMAGES_SCOPE

SCOPE_ORDER = (ANALYSIS_SCOPE, FAMILY_SCOPE, RETAIN_IMAGES_SCOPE)

SCOPE_TEXT = {
    ANALYSIS_SCOPE: {
        "required": True,
        "label_bn": "বিশ্লেষণের সম্মতি",
        "label_en": "Analysis consent",
        "purpose_bn": "প্রেসক্রিপশনের ছবি পড়া ও ওষুধ পর্যালোচনা চালানোর জন্য প্রয়োজন।",
        "purpose_en": "Needed to read prescription images and run the medication check.",
    },
    FAMILY_SCOPE: {
        "required": False,
        "label_bn": "পরিবারের দেখার সম্মতি",
        "label_en": "Family view consent",
        "purpose_bn": "লিঙ্ক করা পরিবারের সদস্যকে শুধু-পড়ার সারসংক্ষেপ দেখতে দেয়।",
        "purpose_en": "Lets linked family members see a read-only summary.",
    },
    RETAIN_IMAGES_SCOPE: {
        "required": False,
        "label_bn": "ছবি সংরক্ষণের সম্মতি",
        "label_en": "Image retention consent",
        "purpose_bn": "প্রেসক্রিপশনের ছবি স্বল্প মেয়াদের চেয়ে বেশি সময় রাখার অনুমতি দেয়।",
        "purpose_en": "Allows prescription images to be kept longer than the short default.",
    },
}

MESSAGES = {
    "ok": (
        "এই রোগীর জন্য বিশ্লেষণের সম্মতি সক্রিয় আছে।",
        "Analysis consent is active for this patient.",
    ),
    "missing": (
        "এই রোগীর জন্য বিশ্লেষণের সম্মতি নথিভুক্ত নেই। সম্মতি নথিভুক্ত না হওয়া পর্যন্ত প্রেসক্রিপশনের ছবি প্রক্রিয়া করা যাবে না।",
        "No analysis consent is recorded for this patient. Prescription images cannot be processed until it is recorded.",
    ),
    "revoked": (
        "বিশ্লেষণের সম্মতি প্রত্যাহার করা হয়েছে। আবার সম্মতি নথিভুক্ত না হওয়া পর্যন্ত প্রেসক্রিপশনের ছবি প্রক্রিয়া করা যাবে না।",
        "Analysis consent was withdrawn. Prescription images cannot be processed until consent is recorded again.",
    ),
}


def _scope_state(scope: str, consents: list) -> dict:
    """`consents` is newest first. Active beats revoked; the newest record of the scope describes the state."""
    of_scope = [c for c in consents if c.scope == scope]
    active = next((c for c in of_scope if c.revoked_at is None), None)
    latest = active or (of_scope[0] if of_scope else None)
    if active is not None:
        status = "active"
    elif latest is not None:
        status = "revoked"
    else:
        status = "missing"
    return {
        "scope": scope,
        "status": status,
        "required": SCOPE_TEXT[scope]["required"],
        "label_bn": SCOPE_TEXT[scope]["label_bn"],
        "label_en": SCOPE_TEXT[scope]["label_en"],
        "purpose_bn": SCOPE_TEXT[scope]["purpose_bn"],
        "purpose_en": SCOPE_TEXT[scope]["purpose_en"],
        "consent_id": active.id if active is not None else None,
        "granted_at": latest.granted_at if latest is not None else None,
        "revoked_at": latest.revoked_at if latest is not None else None,
    }


def compose(patient: Patient, consents: list, links: list, stored_images: int) -> dict:
    """Pure: builds the banner from already-loaded rows (consents newest first; links with `.consent` loaded)."""
    scopes = [_scope_state(scope, consents) for scope in SCOPE_ORDER]
    by_scope = {s["scope"]: s for s in scopes}
    analysis = by_scope[ANALYSIS_SCOPE]["status"]

    ok = analysis == "active"
    message_bn, message_en = MESSAGES["ok" if ok else analysis]

    links_on = [link for link in links if link.is_active]
    with_access = [
        link for link in links_on if link.consent.scope == FAMILY_SCOPE and link.consent.revoked_at is None
    ]
    without_consent = len(links_on) - len(with_access)

    extended = by_scope[RETAIN_IMAGES_SCOPE]["status"] == "active"
    days = settings.PRESCRIPTION_IMAGE_RETAINED_DAYS if extended else settings.PRESCRIPTION_IMAGE_RETENTION_DAYS

    notices = []
    if without_consent:
        notices.append({
            "code": "family_link_without_consent",
            "severity": "warning",
            "message_bn": f"{without_consent}টি পরিবার-লিঙ্ক চালু আছে, কিন্তু সক্রিয় সম্মতি নেই। তারা রোগীর তথ্য দেখতে পারবেন না।",
            "message_en": f"{without_consent} family link(s) are switched on but no longer rest on an active "
                          "family-view consent. They cannot see this patient.",
        })
    if with_access:
        notices.append({
            "code": "family_access",
            "severity": "info",
            "message_bn": f"{len(with_access)} জন পরিবারের সদস্য এই রোগীর শুধু-পড়ার সারসংক্ষেপ দেখতে পারেন।",
            "message_en": f"{len(with_access)} family member(s) can see a read-only summary of this patient.",
        })
    if stored_images and not extended:
        notices.append({
            "code": "images_short_retention",
            "severity": "info",
            "message_bn": f"{stored_images}টি প্রেসক্রিপশনের ছবি সংরক্ষিত আছে; আপলোডের {days} দিনের মধ্যে মুছে ফেলা হবে।",
            "message_en": f"{stored_images} stored prescription image(s) will be deleted {days} days after upload.",
        })

    return {
        "patient_id": patient.id,
        "patient_code": patient.patient_code,
        "level": "ok" if ok else "action_required",
        "blocks": [] if ok else ["prescription_scan"],
        "message_bn": message_bn,
        "message_en": message_en,
        "next_action": None if ok else {"type": "record_consent", "scope": ANALYSIS_SCOPE},
        "scopes": scopes,
        "family": {"links_with_access": len(with_access), "links_without_consent": without_consent},
        "image_retention": {"mode": "extended" if extended else "short", "days": days,
                            "stored_images": stored_images},
        "notices": notices,
    }


def consent_banner(patient: Patient) -> dict:
    """Load what the banner needs (3 queries) and compose it."""
    consents = list(patient.consents.order_by("-granted_at", "-id"))
    links = list(patient.family_links.select_related("consent"))
    stored_images = PrescriptionScan.objects.filter(patient=patient, image_deleted_at__isnull=True).count()
    return compose(patient, consents, links, stored_images)
