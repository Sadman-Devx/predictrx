from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", "admin")
        return self._create(email, password, **extra)


class User(AbstractUser):
    ROLES = [("doctor", "Doctor"), ("pharmacist", "Pharmacist"), ("family", "Family"), ("admin", "Admin")]

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=12, choices=ROLES, default="doctor")
    display_name = models.CharField(max_length=150, blank=True)
    preferred_language = models.CharField(max_length=5, default="bn")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []
    objects = UserManager()

    def __str__(self):
        return self.email
