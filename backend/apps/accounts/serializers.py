from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from . import services
from .models import User


class MeSerializer(serializers.ModelSerializer):
    preferred_language = serializers.ChoiceField(choices=services.LANGUAGES)

    class Meta:
        model = User
        fields = ["id", "email", "role", "display_name", "preferred_language"]
        read_only_fields = ["id", "email", "role"]


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
        return super().validate(attrs)