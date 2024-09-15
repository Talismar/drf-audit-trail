import json

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken, TokenError

User = get_user_model()


def _get_remote_addr(environ: dict):
    return environ.get("HTTP_X_FORWARDED_FOR") or environ.get("REMOTE_ADDR")


def get_ip_addresses(request):
    if isinstance(request, dict):
        return _get_remote_addr(request)

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def get_response_size(response):
    content = getattr(response, "content", None)
    if content is not None and type(content) is bytes:
        return len(response.content)


def get_user_by_raw_authorization_header(request):
    authorization_header = request.headers.get("Authorization")

    if not authorization_header or "Bearer " not in authorization_header:
        return None

    try:
        raw_access_token = authorization_header.split("Bearer ")[1]
        access_token = AccessToken(raw_access_token)
        return User.objects.get(pk=access_token.get("user_id"))
    except (TokenError, User.DoesNotExist, IndexError):
        return None


def get_authenticated_user_by_request(request):
    user = request.user if request.user.is_authenticated else None
    if not user:
        user = request.META.get("drf_request_audit_event", {}).get("user")
    if not user:
        user = get_user_by_raw_authorization_header(request)

    return user


def is_json(data):
    try:
        json.loads(data)
    except BaseException:
        return False
    return True


def get_extra_informations(drf_request_audit_event: dict | None):
    if drf_request_audit_event is None:
        return None

    extra_informations = drf_request_audit_event.get("extra_informations")
    if extra_informations is not None and is_json(extra_informations):
        return extra_informations

    try:
        return json.dumps(extra_informations)
    except Exception:
        return None
