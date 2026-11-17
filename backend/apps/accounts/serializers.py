from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from . import email_verification, password_reset, services
from .models import User


class MeSerializer(serializers.ModelSerializer):
    preferred_language = serializers.ChoiceField(choices=services.LANGUAGES)

    class Meta:
        model = User
        fields = ["id", "email", "role", "display_name", "preferred_language", "email_verified"]
        read_only_fields = ["id", "email", "role", "email_verified"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=services.REGISTERABLE_ROLES, default="doctor")
    preferred_language = serializers.ChoiceField(choices=services.LANGUAGES, default="bn")

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.", code="email_taken")
        return value

    def validate(self, attrs):
        # Run Django's password validators with the user's own attributes (e.g. password too similar to email).
        validate_password(attrs["password"], user=User(email=attrs["email"], display_name=attrs.get("display_name", "")))
        return attrs

    def create(self, validated_data):
        try:
            return services.register_user(**validated_data)
        except IntegrityError:  # two registrations for the same email racing each other
            raise serializers.ValidationError(
                {"email": ["An account with this email already exists."]}, code="email_taken"
            )


class LoginSerializer(TokenObtainPairSerializer):
    """Case-insensitive email login (phone keyboards capitalise the first letter)."""

    def validate(self, attrs):
        attrs[self.username_field] = str(attrs.get(self.username_field, "")).strip().lower()
        data = super().validate(attrs)  # wrong credentials already failed here: nothing below reveals an account
        user = self.user
        if settings.REQUIRE_EMAIL_VERIFICATION and user.role in ("doctor", "pharmacist") and not user.email_verified:
            raise exceptions.PermissionDenied(detail="Please verify your email address first.", code="email_not_verified")
        return data


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})

    def validate(self, attrs):
        user = password_reset.check_reset_token(attrs["uid"], attrs["token"])
        if user is None:
            raise serializers.ValidationError(
                {"token": ["This reset link is invalid or has expired. Please request a new one."]},
                code="invalid_reset_link",
            )
        problems = password_reset.validate_new_password(user, attrs["password"])
        if problems:
            raise serializers.ValidationError({"password": problems}, code="weak_password")
        attrs["user"] = user
        return attrs


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512, required=False)
    email = serializers.EmailField(max_length=254, required=False)
    code = serializers.RegexField(r"^\d{6}$", min_length=6, max_length=6, required=False)

    def validate(self, attrs):
        if attrs.get("token"):
            user = email_verification.user_from_token(attrs["token"])
        elif attrs.get("email") and attrs.get("code"):
            user = email_verification.verify_code(attrs["email"].strip().lower(), attrs["code"])
        else:
            raise serializers.ValidationError(
                {"code": ["Provide the verification code and email address."]}, code="verification_code_required"
            )
        if user is None:
            raise serializers.ValidationError(
                {"code": ["This verification code or link is invalid or has expired. Request a new code."]},
                code="invalid_verification_code",
            )
        attrs["user"] = user
        return attrs


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class ChangePasswordSerializer(serializers.Serializer):
    """Logged-in change of password. The current password must be re-entered (a stolen session alone is not enough)."""

    current_password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})

    def validate_current_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("The current password is not correct.", code="wrong_password")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": ["The new password must be different from the current one."]}, code="same_password"
            )
        problems = password_reset.validate_new_password(user, attrs["new_password"])
        if problems:
            raise serializers.ValidationError({"new_password": problems}, code="weak_password")
        return attrs


class SocialLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=False, allow_blank=True, max_length=4096)       # google
    access_token = serializers.CharField(required=False, allow_blank=True, max_length=4096)   # facebook
    code = serializers.CharField(required=False, allow_blank=True, max_length=2048)           # linkedin
    redirect_uri = serializers.URLField(required=False, allow_blank=True, max_length=512)     # linkedin
    preferred_language = serializers.ChoiceField(choices=services.LANGUAGES, default="bn")

