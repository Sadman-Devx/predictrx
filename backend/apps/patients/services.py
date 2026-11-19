"""Patient, consent and family-link services (business logic; views stay thin).

Rules enforced here (docs/rule.md):
  * Ownership is derived from the authenticated user, never from client input. A foreign or missing patient, consent
    or family link is a plain 404 (existence is not leaked).
  * Consent is explicit and per scope. At most ONE active consent per (patient, scope): granting twice is a 409.
  * Revoking is a state change, never a delete: the row stays as history (`revoked_at`). Revoking a `family_view`
    consent switches off every family link that rests on it; revoking `retain_images` pulls the retention deadline of
    the patient's stored prescription images back to the short default.
  * A family link needs an active `family_view` consent. Family accounts are created by invite from here (the
    self-registration endpoint refuses the `family` role).
  * Audit `meta` never contains names, emails or free text: ids, scopes and counts only (written by the views).
"""
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from apps.accounts.models import User
from apps.clinical.models import Medication, PrescriptionScan

from .models import Consent, FamilyLink, Patient

logger = logging.getLogger(__name__)

# Unambiguous characters only (no 0/O, 1/I/L): codes get read aloud and copied by hand.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8
_MAX_CODE_ATTEMPTS = 5

# The only fields a clinician may change after creation. `owner` and `patient_code` are never client-editable.
UPDATABLE_FIELDS = ("name", "birth_year", "sex", "weight_kg")

ANALYSIS_SCOPE = "analysis"
FAMILY_SCOPE = "family_view"
RETAIN_IMAGES_SCOPE = "retain_images"
MAX_FAMILY_LINKS_PER_PATIENT = 10  # also limits how many invitation e-mails one patient can trigger


class PatientRequestError(APIException):
    """Client-fixable problem. Shape: {"error": {"code": <specific>, "message": ..., "details": {"detail", "code", ...}}}."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"

    def __init__(self, code: str, message: str, *, http_status: int | None = None, **extra):
        super().__init__(detail={"detail": message, "code": code, **extra})
        if http_status:
            self.status_code = http_status


# ------------------------------------------------------------------------------------------------ patients
def generate_patient_code() -> str:
    """Pseudonymous label shown in the UI instead of a name (e.g. PX-7KQ2M9XA)."""
    return "PX-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def patients_for(user):
    """Ownership is derived from the authenticated user, never from client input.

    The queryset also carries what the Patients screen shows next to every patient, loaded with a fixed number of
    queries (no N+1): the medicine count and the ACTIVE consents (`active_consents`, used by `active_consent_scopes`).
    """
    active_consents = Consent.objects.filter(revoked_at__isnull=True)
    return (
        Patient.objects.filter(owner=user)
        .annotate(medication_total=Count("medications"))
        .prefetch_related(Prefetch("consents", queryset=active_consents, to_attr="active_consents"))
        .order_by("-created_at", "-id")
    )


def get_owned_patient(user, pk: int, *, lock: bool = False) -> Patient:
    """The caller's own patient or a plain 404. `lock=True` (inside `transaction.atomic()`) serialises writers, so two
    simultaneous consent grants cannot both pass the 'already active' check."""
    queryset = Patient.objects.filter(pk=pk, owner=user)
    if lock:
        queryset = queryset.select_for_update()
    patient = queryset.first()
    if patient is None:
        raise NotFound()
    return patient


def create_patient(*, owner, data: dict) -> Patient:
    """Create a patient with a server-generated pseudonymous code. Retries on the (very unlikely) code collision."""
    fields = {k: v for k, v in data.items() if k in UPDATABLE_FIELDS}
    for _ in range(_MAX_CODE_ATTEMPTS):
        try:
            with transaction.atomic():  # savepoint, so a collision does not poison the outer transaction
                return Patient.objects.create(owner=owner, patient_code=generate_patient_code(), **fields)
        except IntegrityError:
            continue
    raise RuntimeError("Could not generate a unique patient code")


def update_patient(patient: Patient, data: dict) -> list[str]:
    """Apply changes and return the NAMES of the fields that changed (names only: values are PII-adjacent)."""
    changed = [f for f in UPDATABLE_FIELDS if f in data and getattr(patient, f) != data[f]]
    for f in changed:
        setattr(patient, f, data[f])
    if changed:
        patient.save(update_fields=changed)
    return sorted(changed)


def active_consent_scopes(patient: Patient) -> list[str]:
    """Scopes with an active consent. Uses the `active_consents` prefetch when the patient came from `patients_for`."""
    consents = getattr(patient, "active_consents", None)
    if consents is None:
        consents = list(patient.consents.filter(revoked_at__isnull=True))
    return sorted({c.scope for c in consents})


def medication_count(patient: Patient) -> int:
    total = getattr(patient, "medication_total", None)
    return total if total is not None else patient.medications.count()


# ------------------------------------------------------------------------------------------------ medications
def list_medications(patient):
    """Return all medications for a patient, newest first."""
    return Medication.objects.filter(patient=patient).select_related("drug").order_by("-created_at", "-id")


def add_medication(patient, data: dict) -> Medication:
    """Create a medication record. If drug_id is provided, resolve generic_name from Drug table."""
    from apps.drugs.models import Drug

    drug_id = data.pop("drug_id", None)
    drug = None
    resolution_status = "unresolved"

    if drug_id:
        drug = Drug.objects.get(pk=drug_id)
        resolution_status = "resolved"

    return Medication.objects.create(
        patient=patient,
        raw_text=data.get("raw_text", ""),
        brand_name=data.get("brand_name", ""),
        strength=data.get("strength", ""),
        frequency=data.get("frequency", ""),
        drug=drug,
        resolution_status=resolution_status,
        source="manual",
    )


# ------------------------------------------------------------------------------------------------ consent
def list_consents(patient: Patient):
    """Every consent of the patient, newest first (active and revoked: the history is part of the record)."""
    return patient.consents.order_by("-granted_at", "-id")


def grant_consent(patient: Patient, *, scope: str, granted_by: str) -> Consent:
    """Record a consent. Call inside `transaction.atomic()` with the patient row locked (`get_owned_patient(lock=True)`).

    `granted_at` is the server clock: a client cannot back-date a consent.
    """
    if patient.consents.filter(scope=scope, revoked_at__isnull=True).exists():
        raise PatientRequestError(
            "consent_already_active",
            "This consent is already active for the patient.",
            http_status=status.HTTP_409_CONFLICT,
            scope=scope,
        )
    return Consent.objects.create(patient=patient, scope=scope, granted_by=granted_by, granted_at=timezone.now())


def _shorten_image_retention(patient: Patient) -> int:
    """After `retain_images` is revoked, stored images fall back to the short default window (privacy by default).
    A deadline that is already past is picked up by the hourly purge task. Returns how many scans were changed."""
    window = timedelta(days=settings.PRESCRIPTION_IMAGE_RETENTION_DAYS)
    changed = 0
    for scan in PrescriptionScan.objects.filter(patient=patient, image_deleted_at__isnull=True):
        deadline = scan.created_at + window
        if scan.retain_until > deadline:
            scan.retain_until = deadline
            scan.save(update_fields=["retain_until"])
            changed += 1
    return changed


def revoke_consent(patient: Patient, consent_id: int) -> tuple[Consent, dict | None]:
    """Revoke one consent. Call inside `transaction.atomic()` with the patient row locked.

    Returns (consent, effects). `effects` is None when the consent was ALREADY revoked (nothing changed, so a retry or
    a double click is harmless and writes no second audit entry); otherwise it holds the counts of what the revoke
    switched off: {"family_links_deactivated": n, "images_retention_shortened": n}.
    """
    consent = patient.consents.select_for_update().filter(pk=consent_id).first()
    if consent is None:
        raise NotFound()
    if consent.revoked_at is not None:
        return consent, None

    consent.revoked_at = timezone.now()
    consent.save(update_fields=["revoked_at"])

    effects = {"family_links_deactivated": 0, "images_retention_shortened": 0}
    if consent.scope == FAMILY_SCOPE:
        effects["family_links_deactivated"] = FamilyLink.objects.filter(consent=consent, is_active=True).update(
            is_active=False
        )
    elif consent.scope == RETAIN_IMAGES_SCOPE:
        effects["images_retention_shortened"] = _shorten_image_retention(patient)
    return consent, effects


# ------------------------------------------------------------------------------------------------ family links
def list_family_links(patient: Patient):
    return patient.family_links.select_related("family_user", "consent").order_by("-id")


def _active_family_consent(patient: Patient, consent_id: int | None) -> Consent:
    """The consent a new link rests on: the one the caller named, else the patient's newest active `family_view` one."""
    active = patient.consents.filter(scope=FAMILY_SCOPE, revoked_at__isnull=True)
    if consent_id is not None:
        consent = active.filter(pk=consent_id).first()
        if consent is None:
            raise PatientRequestError("invalid_consent", "Choose an active family-view consent of this patient.")
        return consent
    consent = active.order_by("-granted_at", "-id").first()
    if consent is None:
        raise PatientRequestError(
            "family_consent_required",
            "An active family-view consent is required before a family member can be linked.",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    return consent


def _unavailable() -> PatientRequestError:
    # One generic answer for "this e-mail belongs to a clinician / admin / disabled account": no account enumeration.
    return PatientRequestError("family_account_unavailable", "This e-mail address cannot be linked as a family member.")


def _invite_account(email: str, display_name: str) -> tuple[User, bool]:
    """Create the invited family account (no usable password: the invitee sets one through the e-mailed link)."""
    try:
        with transaction.atomic():  # savepoint: losing a race on the unique e-mail must not poison the outer transaction
            user = User.objects.create_user(
                email=email, password=None, role="family", display_name=display_name, preferred_language="bn"
            )
        return user, True
    except IntegrityError:
        user = User.objects.filter(email__iexact=email).first()
        if user is None or user.role != "family" or not user.is_active:
            raise _unavailable()
        return user, False


def link_family_member(
    patient: Patient, *, email: str, relationship: str, display_name: str = "", consent_id: int | None = None
) -> tuple[FamilyLink, bool]:
    """Link a family user to the patient. Returns (link, invited). Call inside `transaction.atomic()` with the patient
    row locked. `invited` is True when a new family account was created (the view then e-mails the invitation).

    * Needs an active `family_view` consent (403 `family_consent_required`).
    * Only `family`-role accounts can be linked; an unknown e-mail gets a new invited account.
    * An existing usable link is a 409; an old deactivated link is switched on again and pointed at the new consent.
    """
    consent = _active_family_consent(patient, consent_id)
    email = email.strip().lower()
    relationship = relationship.strip()

    user = User.objects.filter(email__iexact=email).first()
    if user is not None and (user.role != "family" or not user.is_active):
        raise _unavailable()

    link = None
    if user is not None:
        link = FamilyLink.objects.select_for_update().filter(patient=patient, family_user=user).first()
        if link is not None and link.is_active and link.consent.revoked_at is None:
            raise PatientRequestError(
                "already_linked", "This family member is already linked.", http_status=status.HTTP_409_CONFLICT
            )

    if FamilyLink.objects.filter(patient=patient, is_active=True).count() >= MAX_FAMILY_LINKS_PER_PATIENT:
        raise PatientRequestError(
            "too_many_family_links",
            "This patient already has the maximum number of linked family members.",
            max_links=MAX_FAMILY_LINKS_PER_PATIENT,
        )

    invited = False
    if user is None:
        user, invited = _invite_account(email, display_name.strip())
        if not invited:  # the account appeared in the meantime: it may already be linked
            link = FamilyLink.objects.select_for_update().filter(patient=patient, family_user=user).first()

    if link is None:
        link = FamilyLink.objects.create(
            patient=patient, family_user=user, relationship=relationship, consent=consent, is_active=True
        )
    else:
        link.relationship = relationship
        link.consent = consent
        link.is_active = True
        link.save(update_fields=["relationship", "consent", "is_active"])
    return link, invited


def unlink_family_member(patient: Patient, link_id: int) -> FamilyLink:
    """Switch a link off (the row stays: who had access, and when, is history). Idempotent."""
    link = patient.family_links.select_for_update().filter(pk=link_id).first()
    if link is None:
        raise NotFound()
    if link.is_active:
        link.is_active = False
        link.save(update_fields=["is_active"])
    return link