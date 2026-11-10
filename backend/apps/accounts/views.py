from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import LoginSerializer, MeSerializer, RegisterSerializer


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