from rest_framework import status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import MeSerializer


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    throttle_scope = "login"


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]


class LogoutView(APIView):
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

    def get_object(self):
        return self.request.user
