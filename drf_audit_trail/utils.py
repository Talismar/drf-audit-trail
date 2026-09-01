import json
import re
from functools import lru_cache

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from rest_framework_simplejwt.tokens import AccessToken, TokenError

from drf_audit_trail.settings import (
    DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE,
    DRF_AUDIT_TRAIL_NOTSAVE_REQUEST_BODY_URLS,
    DRF_AUDIT_TRAIL_NOTSAVE_RESPONSE_BODY_URLS,
)

from .settings import DRF_AUDIT_TRAIL_USER_PK_NAME


@lru_cache(maxsize=128)
def get_user_by_pk_name(value: str | None):
    try:
        User = get_user_model()
        filter_param = {DRF_AUDIT_TRAIL_USER_PK_NAME: value}
        user = User.objects.filter(**filter_param).first()
        if user is not None:
            return user
    except ValueError:
        pass


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

    if not authorization_header or (
        "Bearer " not in authorization_header and "Token " not in authorization_header
    ):
        return None

    try:
        User = get_user_model()
        raw_access_token = (
            authorization_header.split("Bearer ")[1]
            if "Bearer " in authorization_header
            else authorization_header.split("Token ")[1]
        )
        access_token = AccessToken(raw_access_token)
        return User.objects.get(pk=access_token.get("user_id"))
    except (TokenError, ObjectDoesNotExist, IndexError):
        return None


def get_authenticated_user_by_request(request):
    user = request.user if request.user.is_authenticated else None
    if not user:
        user = request.META.get("drf_request_audit_event", {}).get("user")
    if not user:
        user = get_user_by_raw_authorization_header(request)

    return user


def get_user_role_by_django_groups(user, request=None):
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    try:
        group = user.groups.order_by("pk").first()
    except AttributeError:
        return None

    if group is None:
        return None
    return group.name


def get_global_audit_actor_role(
    *,
    request=None,
    user=None,
    actor_type=None,
    model=None,
    ref_name=None,
    ref_id=None,
    **kwargs,
):
    if actor_type == "System":
        return DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE

    authenticated_user = user or get_authenticated_user_by_request(request)
    if authenticated_user is None:
        return "Anonymous"

    role = get_user_role_by_django_groups(authenticated_user, request=request)
    if role is not None:
        return role

    return "No Role"


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


def deserialize_audit_value(value):
    if value in (None, ""):
        return None

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def get_request_body(request: HttpRequest):
    if audit_enable_by_url_configs(DRF_AUDIT_TRAIL_NOTSAVE_REQUEST_BODY_URLS, request):
        return None

    try:
        if request.content_type == "application/json":
            body_unicode = request.body.decode("utf-8")
            return json.dumps(body_unicode, ensure_ascii=False)
    except Exception:
        pass
    return None


def get_response_body(request: HttpRequest, response):
    if audit_enable_by_url_configs(DRF_AUDIT_TRAIL_NOTSAVE_RESPONSE_BODY_URLS, request):
        return None

    try:
        if response.get("Content-Type") == "application/json":
            body_unicode = response.content.decode("utf-8")
            return json.dumps(body_unicode, ensure_ascii=False)
    except Exception:
        pass
    return None


def audit_enable_by_url_configs(url_configs: list, request: HttpRequest):
    for url in url_configs:
        if isinstance(url, dict):
            route = url.get("route")
            method = url.get("method")

            if (
                (isinstance(route, str) and isinstance(method, str))
                and bool(re.match(route, request.path))
                and (method == request.method or method == "ALL")
            ):
                return True

            continue

        if bool(re.match(url, request.path)):
            return True

    return False
