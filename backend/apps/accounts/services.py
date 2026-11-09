from .models import User

# Self-service registration is limited to clinical roles.
# `family` accounts are created by invite (Day 9), `admin` only via createsuperuser.
REGISTERABLE_ROLES = ("doctor", "pharmacist")
LANGUAGES = ("bn", "en")


def register_user(*, email: str, password: str, display_name: str = "", role: str = "doctor",
                  preferred_language: str = "bn") -> User:
    """Create a clinician account. The role is validated by the serializer against REGISTERABLE_ROLES."""
    if role not in REGISTERABLE_ROLES:  # defence in depth: never create admin/family from this path
        raise ValueError(f"Role '{role}' cannot self-register")
    return User.objects.create_user(
        email=email,
        password=password,
        role=role,
        display_name=display_name,
        preferred_language=preferred_language,
    )