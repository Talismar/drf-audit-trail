import logging
import json
from collections.abc import Mapping
from contextlib import ContextDecorator
from functools import wraps
from inspect import Parameter, signature

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.http import HttpRequest
from django.utils.module_loading import import_string

from .config import get_pg_audit_config
from .constants import SYSTEM, USER
from drf_audit_trail.settings import DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE

PG_AUDIT_EXTRA_INFORMATIONS_META_KEY = "drf_pg_audit_extra_informations"
logger = logging.getLogger(__name__)

ACTION_ID_SETTING = "app.action_id"
SOURCE_SETTING = "app.source"
REF_NAME_SETTING = "app.ref_name"
REF_ID_SETTING = "app.ref_id"
USER_SETTING = "app.user"
ACTOR_TYPE_SETTING = "app.actor_type"
ACTOR_ROLE_SETTING = "app.actor_role"
URL_SETTING = "app.url"
EXTRA_INFORMATIONS_SETTING = "app.extra_informations"
REASON_FOR_CHANGE_SETTING = "app.reason_for_change"

PG_SETTINGS = (
    ACTION_ID_SETTING,
    SOURCE_SETTING,
    REF_NAME_SETTING,
    REF_ID_SETTING,
    USER_SETTING,
    ACTOR_TYPE_SETTING,
    ACTOR_ROLE_SETTING,
    URL_SETTING,
    EXTRA_INFORMATIONS_SETTING,
    REASON_FOR_CHANGE_SETTING,
)


class audit(ContextDecorator):
    def __init__(
        self,
        source=None,
        username=None,
        actor_role=None,
        callback=None,
        request=None,
        actor_type=None,
        reason_for_change=None,
        extra_informations=None,
        extra_informations_getter=None,
    ):
        self.source = source
        self.username = username
        self.actor_role = actor_role
        self.callback = callback
        self.request = request
        self.actor_type = actor_type
        self.reason_for_change = reason_for_change
        self.extra_informations = extra_informations
        self.extra_informations_getter = extra_informations_getter
        self.ref_name = None
        self.ref_id = None
        self.url = None
        self.user = None
        self.metadata = {}
        self._previous_settings = None

    def __call__(self, func):
        source = self.source or f"{func.__module__}.{func.__qualname__}".lower()

        @wraps(func)
        def wrapper(*args, **kwargs):
            context = self._clone(source=source)
            context._configure_from_call(args, kwargs)
            with context:
                result = func(*args, **kwargs)
            return result

        return wrapper

    def __enter__(self):
        if self.request is not None:
            self._configure_from_request(self.request)

        self._previous_settings = get_current_pg_settings()
        actor_type = self._resolve_actor_type()
        reason_for_change = self._resolve_reason_for_change()
        extra_informations = self._resolve_extra_informations(
            actor_type=actor_type,
            reason_for_change=reason_for_change,
        )
        actor_role = self._resolve_actor_role(actor_type=actor_type)

        set_pg_settings(
            {
                ACTION_ID_SETTING: "",
                SOURCE_SETTING: self._resolve_setting_value(
                    SOURCE_SETTING, self.source
                ),
                REF_NAME_SETTING: self._resolve_setting_value(
                    REF_NAME_SETTING, self.ref_name
                ),
                REF_ID_SETTING: self._resolve_setting_value(
                    REF_ID_SETTING, self.ref_id
                ),
                USER_SETTING: self._resolve_setting_value(USER_SETTING, self.username),
                ACTOR_TYPE_SETTING: actor_type,
                ACTOR_ROLE_SETTING: actor_role,
                URL_SETTING: self._resolve_setting_value(URL_SETTING, self.url),
                EXTRA_INFORMATIONS_SETTING: serialize_extra_informations(
                    extra_informations
                ),
                REASON_FOR_CHANGE_SETTING: serialize_reason_for_change(
                    reason_for_change
                ),
            }
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._previous_settings is not None:
            set_pg_settings(self._previous_settings)
        return False

    def _clone(self, source=None):
        context = self.__class__(
            source=source if source is not None else self.source,
            username=self.username,
            actor_role=self.actor_role,
            callback=self.callback,
            request=self.request,
            actor_type=self.actor_type,
            reason_for_change=self.reason_for_change,
            extra_informations=self.extra_informations,
            extra_informations_getter=self.extra_informations_getter,
        )
        context.ref_name = self.ref_name
        context.ref_id = self.ref_id
        context.url = self.url
        context.user = self.user
        return context

    def _configure_from_call(self, args, kwargs):
        request = self.request or get_request_from_call(args, kwargs)
        metadata = {}

        if self.callback:
            metadata = self.callback(*args, **kwargs) or {}
            model = metadata.get("model")
            if model is not None:
                self.ref_name = metadata.get("ref_name") or model._meta.db_table
            else:
                self.ref_name = metadata.get("ref_name") or self.ref_name

            self.ref_id = metadata.get("pk", metadata.get("ref_id", self.ref_id))
            self.url = metadata.get("url") or self.url
            self.username = metadata.get("username") or self.username
            self.actor_role = metadata.get("actor_role") or self.actor_role
            self.actor_type = self.actor_type or metadata.get("actor_type")
            self.reason_for_change = self.reason_for_change or metadata.get(
                "reason_for_change"
            )
            self.extra_informations = merge_extra_informations(
                metadata.get("extra_informations"),
                self.extra_informations,
            )
            request = metadata.get("request") or request

        if request is not None:
            self.request = request
            self._configure_from_request(request)

        self.metadata = metadata

    def _configure_from_request(self, request):
        self.url = self.url or get_request_url(request)
        self.username = self.username or get_request_username(request)
        self.user = self.user or get_request_user(request)

    def _resolve_setting_value(self, setting_name, value):
        if has_value(value):
            return str(value)
        return self._previous_settings.get(setting_name) or ""

    def _resolve_actor_type(self):
        if has_value(self.actor_type):
            return str(self.actor_type)

        previous_actor_type = self._previous_settings.get(ACTOR_TYPE_SETTING)
        if has_value(previous_actor_type):
            return previous_actor_type

        return USER

    def _resolve_actor_role(self, actor_type=None):
        if has_value(self.actor_role):
            return str(self.actor_role)

        previous_actor_role = self._previous_settings.get(ACTOR_ROLE_SETTING)
        if has_value(previous_actor_role):
            return previous_actor_role

        current_actor_type = actor_type or self.actor_type
        if current_actor_type == SYSTEM:
            return DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE

        getter = get_pg_audit_config().get("default_actor_role_getter")
        if getter in (None, ""):
            return None
        if isinstance(getter, str):
            getter = import_string(getter)

        kwargs = {
            "request": self.request,
            "user": self.user or get_request_user(self.request),
            "source": self.source,
            "username": self.username,
            "actor_type": actor_type or self.actor_type,
            "reason_for_change": self.reason_for_change,
            "ref_name": self.ref_name,
            "ref_id": self.ref_id,
            "url": self.url,
            "metadata": self.metadata,
            "extra_informations": self.extra_informations,
        }
        model = self.metadata.get("model")
        if model is not None:
            kwargs["model"] = model

        try:
            return call_with_supported_kwargs(getter, kwargs)
        except Exception as exc:
            logger.warning("Unable to resolve pg_audit actor role: %s", exc)
            return None

    def _resolve_reason_for_change(self):
        if self.reason_for_change not in (None, ""):
            return normalize_reason_for_model_columns(
                self.reason_for_change,
                self.metadata.get("model"),
            )

        config = get_pg_audit_config()
        request_reason = get_request_reason_for_change(
            self.request,
            config.get("reason_for_change_key"),
        )
        if request_reason not in (None, ""):
            return normalize_reason_for_model_columns(
                request_reason,
                self.metadata.get("model"),
            )

        previous_reason = deserialize_reason_for_change(
            self._previous_settings.get(REASON_FOR_CHANGE_SETTING)
        )
        if previous_reason not in (None, ""):
            return previous_reason

        return None

    def _resolve_extra_informations(self, *, actor_type=None, reason_for_change=None):
        previous_value = deserialize_extra_informations(
            self._previous_settings.get(EXTRA_INFORMATIONS_SETTING)
        )
        getter_value = self._call_extra_informations_getter(
            actor_type=actor_type,
            reason_for_change=reason_for_change,
        )
        request_value = get_request_extra_informations(self.request)

        extra_informations = merge_extra_informations(previous_value, getter_value)
        extra_informations = merge_extra_informations(extra_informations, request_value)
        return merge_extra_informations(extra_informations, self.extra_informations)

    def _call_extra_informations_getter(
        self, *, actor_type=None, reason_for_change=None
    ):
        getter = self.extra_informations_getter or get_pg_audit_config().get(
            "default_extra_informations_getter"
        )
        if getter in (None, ""):
            return None
        if isinstance(getter, str):
            getter = import_string(getter)

        kwargs = {
            "request": self.request,
            "source": self.source,
            "username": self.username,
            "actor_type": actor_type or self.actor_type,
            "reason_for_change": reason_for_change or self.reason_for_change,
            "ref_name": self.ref_name,
            "ref_id": self.ref_id,
            "url": self.url,
            "metadata": self.metadata,
            "extra_informations": self.extra_informations,
        }
        model = self.metadata.get("model")
        if model is not None:
            kwargs["model"] = model

        return call_with_supported_kwargs(getter, kwargs)

    @staticmethod
    def ref(obj):
        set_pg_settings(
            {
                REF_NAME_SETTING: obj._meta.db_table,
                REF_ID_SETTING: obj.pk,
            }
        )

    @staticmethod
    def set_extra_informations(extra_informations, merge=True):
        current_value = None
        if merge:
            current_settings = get_current_pg_settings([EXTRA_INFORMATIONS_SETTING])
            current_value = deserialize_extra_informations(
                current_settings.get(EXTRA_INFORMATIONS_SETTING)
            )

        set_pg_settings(
            {
                EXTRA_INFORMATIONS_SETTING: serialize_extra_informations(
                    merge_extra_informations(current_value, extra_informations)
                )
            }
        )

    @staticmethod
    def set_reason_for_change(reason_for_change):
        set_pg_settings(
            {REASON_FOR_CHANGE_SETTING: serialize_reason_for_change(reason_for_change)}
        )


def system_audit(
    *,
    source=None,
    username="system",
    actor_role=None,
    reason_for_change=None,
    extra_informations=None,
    extra_informations_getter=None,
):
    return audit(
        source=source,
        username=username,
        actor_role=actor_role,
        actor_type=SYSTEM,
        reason_for_change=reason_for_change,
        extra_informations=extra_informations,
        extra_informations_getter=extra_informations_getter,
    )


def get_current_pg_settings(setting_names=None):
    setting_names = setting_names or PG_SETTINGS
    values = {}
    with connection.cursor() as cursor:
        for setting_name in setting_names:
            cursor.execute("SELECT current_setting(%s, true)", [setting_name])
            values[setting_name] = cursor.fetchone()[0]
    return values


def set_pg_settings(values):
    with connection.cursor() as cursor:
        for setting_name, value in values.items():
            cursor.execute(
                "SELECT set_config(%s, %s, false)",
                [setting_name, "" if value is None else str(value)],
            )


def get_request_from_call(args, kwargs):
    request = kwargs.get("request")
    if looks_like_request(request):
        return request

    for arg in args:
        if looks_like_request(arg):
            return arg

        request = getattr(arg, "request", None)
        if looks_like_request(request):
            return request

    return None


def looks_like_request(value):
    return isinstance(value, HttpRequest) or (
        hasattr(value, "META") and hasattr(value, "user")
    )


def get_request_url(request):
    if request is None:
        return None
    if hasattr(request, "get_full_path"):
        return request.get_full_path()

    django_request = getattr(request, "_request", None)
    if django_request is not None and hasattr(django_request, "get_full_path"):
        return django_request.get_full_path()

    return None


def get_request_username(request):
    if request is None:
        return None

    user = get_request_user(request)
    if user is None:
        return None

    if hasattr(user, "get_username"):
        return user.get_username()

    username = getattr(user, "username", None)
    if username is not None:
        return username

    return str(user)


def get_request_user(request):
    if request is None:
        return None

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user


def get_request_extra_informations(request):
    if request is None:
        return None
    return getattr(request, "META", {}).get(PG_AUDIT_EXTRA_INFORMATIONS_META_KEY)


def get_request_reason_for_change(request, reason_key):
    if request is None or not reason_key:
        return None

    data = get_value_from_request_mapping(safe_getattr(request, "data"), reason_key)
    if data not in (None, ""):
        return normalize_request_reason_value(data)

    django_request = getattr(request, "_request", request)
    post_value = get_value_from_request_mapping(
        safe_getattr(django_request, "POST"),
        reason_key,
    )
    if post_value not in (None, ""):
        return normalize_request_reason_value(post_value)

    body_data = get_json_request_body(django_request)
    body_value = get_value_from_request_mapping(body_data, reason_key)
    if body_value not in (None, ""):
        return normalize_request_reason_value(body_value)

    return None


def safe_getattr(obj, attr_name):
    try:
        return getattr(obj, attr_name, None)
    except Exception:
        return None


def get_value_from_request_mapping(data, key):
    if data in (None, ""):
        return None
    if hasattr(data, "get"):
        return data.get(key)
    if isinstance(data, Mapping):
        return data.get(key)
    return None


def normalize_request_reason_value(value):
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        return value

    stripped_value = value.strip()
    if not stripped_value:
        return None
    if not stripped_value.startswith("{"):
        return value

    try:
        parsed_value = json.loads(stripped_value)
    except (TypeError, ValueError):
        return value

    if isinstance(parsed_value, Mapping):
        return dict(parsed_value)
    return value


def normalize_reason_for_model_columns(reason_for_change, model):
    if not isinstance(reason_for_change, Mapping) or model is None:
        return reason_for_change

    normalized_reason = dict(reason_for_change)
    for field_name, reason in reason_for_change.items():
        try:
            field = model._meta.get_field(field_name)
        except Exception:
            continue

        column_name = getattr(field, "column", None)
        if column_name:
            normalized_reason.setdefault(column_name, reason)

    return normalized_reason


def get_json_request_body(request):
    try:
        raw_body = request.body
    except Exception:
        return None

    if not raw_body:
        return None

    try:
        if isinstance(raw_body, bytes):
            raw_body = raw_body.decode(getattr(request, "encoding", None) or "utf-8")
        parsed_body = json.loads(raw_body)
    except (TypeError, UnicodeDecodeError, ValueError):
        return None

    if isinstance(parsed_body, Mapping):
        return parsed_body
    return None


def serialize_extra_informations(value):
    if value in (None, ""):
        return ""

    if isinstance(value, str) and is_json(value):
        return value

    try:
        return json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def deserialize_extra_informations(value):
    if value in (None, ""):
        return None

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def serialize_reason_for_change(value):
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False)
    except TypeError:
        return str(value)


def deserialize_reason_for_change(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value

    stripped_value = value.strip()
    if not stripped_value.startswith("{"):
        return value

    try:
        parsed_value = json.loads(stripped_value)
    except (TypeError, ValueError):
        return value

    return parsed_value if isinstance(parsed_value, dict) else value


def merge_extra_informations(base_value, override_value):
    if override_value in (None, ""):
        return base_value
    if base_value in (None, ""):
        return override_value
    if isinstance(base_value, dict) and isinstance(override_value, dict):
        merged_value = base_value.copy()
        merged_value.update(override_value)
        return merged_value
    return override_value


def call_with_supported_kwargs(func, kwargs):
    try:
        func_signature = signature(func)
    except (TypeError, ValueError):
        return func(**kwargs)

    if any(
        parameter.kind == Parameter.VAR_KEYWORD
        for parameter in func_signature.parameters.values()
    ):
        return func(**kwargs)

    accepted_kwargs = {
        name: value
        for name, value in kwargs.items()
        if name in func_signature.parameters
    }
    return func(**accepted_kwargs)


def has_value(value):
    return value not in (None, "")


def is_json(value):
    try:
        json.loads(value)
    except (TypeError, ValueError):
        return False
    return True
