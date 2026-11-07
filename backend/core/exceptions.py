from rest_framework.views import exception_handler


class OutOfEvidence(Exception):
    """Raised when a finding would be saved without evidence."""


def api_exception_handler(exc, context):
    """Consistent error shape: {"error": {"code": ..., "message": ..., "details": ...}}"""
    response = exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    code = getattr(getattr(exc, "detail", None), "code", None) or response.status_text.lower().replace(" ", "_")
    message = data.get("detail") if isinstance(data, dict) and "detail" in data else "Request failed"
    details = None if (isinstance(data, dict) and set(data) == {"detail"}) else data
    response.data = {"error": {"code": str(code), "message": str(message), "details": details}}
    return response
