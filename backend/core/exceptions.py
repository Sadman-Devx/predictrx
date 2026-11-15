"""Consistent API error shape for every failure under /api/.

    {"error": {"code": "<machine_code>", "message": "<human text>", "details": <null | object | list>}}

* `code`    stable machine code. Specific business errors (e.g. `unresolved_medications`) are promoted to the top;
            validation failures are `validation_error`; everything else is DRF's own code (`not_found`,
            `permission_denied`, `throttled`, ...). The frontend switches on this, never on `message`.
* `message` short human text (never a stack trace, never a SQL error, never PII).
* `details` field errors for validation, extra context for business errors (e.g. the offending medication ids),
            `{"retry_after_seconds": n}` for throttling, otherwise null.

An exception that is NOT an API error (a bug, a database outage) is logged with its stack trace on the server and
the client gets a generic `server_error` JSON body: no internals leak, and the response is never an HTML page.
"""
import logging

from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

logger = logging.getLogger(__name__)


class OutOfEvidence(Exception):
    """Raised when a finding would be saved without evidence."""


def error_payload(code: str, message: str, details=None) -> dict:
    return {"error": {"code": str(code), "message": str(message), "details": details}}


def _unhandled(exc: Exception, context: dict) -> Response:
    view = context.get("view")
    logger.error(
        "unhandled exception in %s: %s",
        view.__class__.__name__ if view is not None else "?",
        exc.__class__.__name__,
        exc_info=exc,
    )
    set_rollback()  # mirror what DRF does for handled errors when ATOMIC_REQUESTS is on
    return Response(error_payload("server_error", "Something went wrong on our side. Please try again."), status=500)


def api_exception_handler(exc, context):
    """DRF `EXCEPTION_HANDLER`. See the module docstring for the shape."""
    response = exception_handler(exc, context)
    if response is None:
        return _unhandled(exc, context)

    data = response.data
    only_detail = isinstance(data, dict) and set(data) == {"detail"}
    message = str(data["detail"]) if isinstance(data, dict) and "detail" in data else "Request failed"
    details = None if only_detail else data

    if isinstance(exc, drf_exceptions.ValidationError):
        code, message = "validation_error", "Some fields are invalid."
    elif isinstance(data, dict) and isinstance(data.get("code"), str):
        code = data["code"]  # specific business error raised as APIException(detail={"detail":..., "code":...})
    else:
        detail = getattr(exc, "detail", None)
        code = getattr(detail, "code", None) or response.status_text.lower().replace(" ", "_")

    if isinstance(exc, drf_exceptions.Throttled):
        details = {"retry_after_seconds": int(exc.wait) if exc.wait is not None else None}

    response.data = error_payload(code, message, details)
    return response