import hmac
from functools import wraps

from flask import current_app, request

from errors import ApiError


def _matches(token, expected):
    return bool(expected) and hmac.compare_digest(token, expected)


def admin_required(fn):
    """401 = no/invalid token, 403 = valid token but not an administrator."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or not header[7:].strip():
            raise ApiError(401, "UNAUTHENTICATED", "Missing bearer token.")
        token = header[7:].strip()
        if _matches(token, current_app.config.get("ADMIN_TOKEN")):
            return fn(*args, **kwargs)
        if _matches(token, current_app.config.get("STUDENT_TOKEN")):
            raise ApiError(403, "FORBIDDEN", "Administrator role required.")
        raise ApiError(401, "INVALID_TOKEN", "Invalid bearer token.")

    return wrapper
