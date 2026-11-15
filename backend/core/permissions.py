from rest_framework.permissions import BasePermission


class IsPatientOwner(BasePermission):
    """Object-level: the clinician who owns the patient. Ownership is derived server-side."""

    def has_object_permission(self, request, view, obj):
        patient = getattr(obj, "patient", obj)
        return patient.owner_id == request.user.id


class HasRole(BasePermission):
    allowed_roles: tuple[str, ...] = ()

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role in self.allowed_roles)


class IsDoctorOrPharmacist(HasRole):
    allowed_roles = ("doctor", "pharmacist")


class IsAdminRole(HasRole):
    allowed_roles = ("admin",)


class IsFamilyRole(HasRole):
    """Family (NRB) accounts. Role only: access to a specific patient still needs an active FamilyLink + Consent,
    checked on every request in apps/patients/family.py."""

    allowed_roles = ("family",)