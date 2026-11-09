import secrets

from django.db import IntegrityError, transaction

from .models import Patient

# Unambiguous characters only (no 0/O, 1/I/L): codes get read aloud and copied by hand.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8
_MAX_CODE_ATTEMPTS = 5

# The only fields a clinician may change after creation. `owner` and `patient_code` are never client-editable.
UPDATABLE_FIELDS = ("birth_year", "sex", "weight_kg")


def generate_patient_code() -> str:
    """Pseudonymous label shown in the UI instead of a name (e.g. PX-7KQ2M9XA)."""
    return "PX-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def patients_for(user):
    """Ownership is derived from the authenticated user, never from client input."""
    return Patient.objects.filter(owner=user).order_by("-created_at", "-id")


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