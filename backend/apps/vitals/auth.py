from rest_framework import authentication, exceptions

from .models import Device


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    """Device sends header:  X-Device-Token: <token>"""

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
