from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.exceptions import error_payload

from . import cookies, email_verification, password_reset, social
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    SocialLoginSerializer,
    VerifyEmailSerializer,
)


class RegisterView(CreateAPIView):
    """POST /api/auth/register/ — create an unverified clinical account and email an OTP.

    Returns the profile, not tokens. A mail problem never fails the registration (the user can ask for a new link).
    """

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []  # public endpoint: a stale/invalid token header must not cause a 401
    throttle_scope = "register"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        email_sent = email_verification.send_verification_code(user)
        data = dict(MeSerializer(user).data)
        data["verification_email_sent"] = email_sent
        return Response(data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ — access token in the body, refresh token in the httpOnly session cookie."""

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            cookies.attach_refresh(response, response.data.get("refresh"))
        return response


class RefreshView(TokenRefreshView):
    """POST /api/auth/token/refresh/ — new access token. The refresh token comes from the body (API clients) or,
    when the body has none, from the httpOnly session cookie (the web app, also right after a page reload)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request, *args, **kwargs):
        body = request.data if hasattr(request.data, "get") else {}
        token = body.get("refresh") or request.COOKIES.get(settings.AUTH_REFRESH_COOKIE, "")
        response = None
        if token:
            serializer = self.get_serializer(data={"refresh": token})
            try:
                serializer.is_valid(raise_exception=True)
            except (TokenError, AuthenticationFailed):
                pass
            else:
                response = Response(serializer.validated_data, status=status.HTTP_200_OK)
                cookies.attach_refresh(response, serializer.validated_data.get("refresh"))
        if response is None:
            response = Response(
                error_payload("token_not_valid", "The session has expired. Please log in again."),
                status=status.HTTP_401_UNAUTHORIZED,
            )
            cookies.clear_refresh_cookie(response)
        return response


class LogoutView(APIView):
    """POST /api/auth/logout/ — blacklist the refresh token (body or cookie) and clear the cookie.

    Open to anyone on purpose: a person whose access token already expired must still be able to end the session.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        tags=["Auth"],
        summary="Log out (blacklist the refresh token, clear the session cookie)",
        request=inline_serializer("LogoutRequest", {"refresh": serializers.CharField(required=False)}),
        responses={204: OpenApiResponse(description="Refresh token blacklisted"),
                   400: OpenApiResponse(description="Invalid refresh token")},
    )
    def post(self, request):
        body = request.data if hasattr(request.data, "get") else {}
        token = body.get("refresh") or request.COOKIES.get(settings.AUTH_REFRESH_COOKIE, "")
        try:
            RefreshToken(token).blacklist()
        except TokenError:
            response = Response(error_payload("invalid_token", "Invalid refresh token"),
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            response = Response(status=status.HTTP_204_NO_CONTENT)
        cookies.clear_refresh_cookie(response)
        return response


class MeView(RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class VerifyEmailView(APIView):
    """POST /api/auth/verify-email/ {email, code} or legacy {token} — confirm the mailbox."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "email_verify"

    @extend_schema(tags=["Auth"], summary="Verify the email address with an OTP or legacy link",
                   request=VerifyEmailSerializer, responses={200: OpenApiResponse(description="Email verified")})
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        if not user.email_verified:
            email_verification.mark_verified(user)
        return Response({"detail": "Email verified. You can log in now."})


class ResendVerificationView(APIView):
    """POST /api/auth/resend-verification/ {email} — new OTP. Always 202 to avoid account enumeration."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "email_verify_resend"

    @extend_schema(tags=["Auth"], summary="Request a new verification code",
                   request=ResendVerificationSerializer, responses={202: OpenApiResponse(description="Accepted")})
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email_verification.resend(serializer.validated_data["email"])
        return Response({"detail": "If this account still needs verification, a new code has been sent."},
                        status=status.HTTP_202_ACCEPTED)


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
        password_reset.set_new_password(
            serializer.validated_data["user"], serializer.validated_data["password"], proves_email=True
        )
        return Response({"detail": "Password changed. Please log in."})


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/ {current_password, new_password} — for a signed-in user.

    Every refresh token of the user is blacklisted afterwards (same rule as the emailed reset) and the session cookie
    is cleared, so the client must log in again; the short-lived access token of the current tab simply expires.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "password_change"

    @extend_schema(tags=["Auth"], summary="Change the password of the signed-in user",
                   request=ChangePasswordSerializer, responses={200: OpenApiResponse(description="Password changed")})
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        password_reset.set_new_password(request.user, serializer.validated_data["new_password"])
        response = Response({"detail": "Password changed. Please log in again."})
        cookies.clear_refresh_cookie(response)
        return response


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
        response = Response({"access": str(refresh.access_token), "refresh": str(refresh)})
        cookies.attach_refresh(response, str(refresh))
        return response
