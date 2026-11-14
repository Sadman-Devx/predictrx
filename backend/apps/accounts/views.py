from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import password_reset, social
from .serializers import (
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    SocialLoginSerializer,
)


class RegisterView(CreateAPIView):
    """POST /api/auth/register/ — create a doctor/pharmacist account. Returns the profile, not tokens."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []  # public endpoint: a stale/invalid token header must not cause a 401
    throttle_scope = "register"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(MeSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_scope = "login"


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]


class LogoutView(APIView):
    @extend_schema(
        tags=["Auth"],
        summary="Log out (blacklist the refresh token)",
        request=inline_serializer("LogoutRequest", {"refresh": serializers.CharField()}),
        responses={204: OpenApiResponse(description="Refresh token blacklisted"),
                   400: OpenApiResponse(description="Invalid refresh token")},
    )
    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            return Response({"error": {"code": "invalid_token", "message": "Invalid refresh token"}},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ {email} — email a reset link. Always 202, whether or not the account exists."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "password_reset"

    @extend_schema(tags=["Auth"], summary="Request a password-reset email",
                   request=PasswordResetRequestSerializer, responses={202: OpenApiResponse(description="Accepted")})
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password_reset.send_reset_email(serializer.validated_data["email"])
        return Response({"detail": "If an account exists for this email, a reset link has been sent."},
                        status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ {uid, token, password} — set a new password from the emailed link."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "password_reset_confirm"

    @extend_schema(tags=["Auth"], summary="Set a new password using the emailed link",
                   request=PasswordResetConfirmSerializer, responses={200: OpenApiResponse(description="Password changed")})
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password_reset.set_new_password(serializer.validated_data["user"], serializer.validated_data["password"])
        return Response({"detail": "Password changed. Please log in."})


class SocialLoginView(APIView):
    """POST /api/auth/social/<google|facebook|linkedin>/ — exchange a provider credential for our JWT pair."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "social"

    @extend_schema(tags=["Auth"], summary="Sign in with Google / Facebook / LinkedIn",
                   request=SocialLoginSerializer,
                   responses={200: inline_serializer("SocialTokens", {"access": serializers.CharField(),
                                                                       "refresh": serializers.CharField()})})
    def post(self, request, provider: str):
        if provider not in social.PROVIDERS:
            return Response({"detail": "Unknown provider."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SocialLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = social.login_with_provider(provider, data, data["preferred_language"])
        except social.SocialAuthError as exc:
            return Response({"error": {"code": exc.code, "message": exc.message, "details": None}}, status=exc.status)
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})

