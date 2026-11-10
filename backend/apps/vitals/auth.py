from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication, exceptions
from rest_framework import authentication, exceptions

from .models import Device


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    """Device sends header:  X-Device-Token: <token>"""


class DeviceTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    """Describes the X-Device-Token header in the OpenAPI schema (documentation only)."""

    target_class = "apps.vitals.auth.DeviceTokenAuthentication"
    name = "deviceToken"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "X-Device-Token"}
    def authenticate(self, request):
        token = request.headers.get("X-Device-Token")
        if not token:
            return None
        try:
            device = Device.objects.get(token_hash=Device.hash_token(token), is_active=True)
        except Device.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid device token")
        return (None, device)  # request.user=None, request.auth=device

    def authenticate_header(self, request):
        return "X-Device-Token"
