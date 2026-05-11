import asyncio
from functools import wraps
from inspect import Parameter, signature

from django.conf import settings
from django.utils.module_loading import import_string

from drf_audit_trail.models import AuditLogEntry
from drf_audit_trail.settings import (
    DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_IDENTIFIER,
    DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE,
    DRF_AUDIT_TRAIL_USER_PK_NAME,
    DRF_AUDIT_TRAIL_USER_ROLE_GETTER,
)
from drf_audit_trail.utils import (
    get_authenticated_user_by_request,
    serialize_audit_value,
)

PENDING_AUDIT_LOG_ENTRIES_KEY = "drf_audit_trail_pending_audit_log_entries"


class AuditLogDraft:
    entry_fields = (
        "actor_identifier",
        "actor_role",
        "actor_type",
        "event_type",
        "action_description",
        "content_type",
        "object_id",
        "object_repr",
        "field_name",
        "old_values",
        "new_values",
        "reason_for_change",
        "extra_informations",
    )

    def __init__(self, content_object=None, **kwargs):
        for field_name in self.entry_fields:
            setattr(self, field_name, kwargs.get(field_name))

        if self.actor_type is None:
            self.actor_type = AuditLogEntry.USER

        if content_object is not None:
            self.set_content_object(content_object)

    def set_content_object(self, obj):
        self.content_type = f"{obj._meta.app_label}.{obj._meta.model_name}"
        self.object_id = str(obj.pk)
        self.object_repr = str(obj)
        return self

    def to_entry_kwargs(self, request_audit_event=None, request=None):
        actor_identifier = self.actor_identifier or self._get_actor_identifier(request)
        if actor_identifier is not None:
            actor_identifier = str(actor_identifier)

        actor_role = self.actor_role or self._get_actor_role(request)
        if actor_role is not None:
            actor_role = str(actor_role)

        return {
            "request": request_audit_event,
            "actor_identifier": actor_identifier,
            "actor_role": actor_role,
            "actor_type": self.actor_type,
            "event_type": self.event_type,
            "action_description": self.action_description,
            "content_type": self.content_type,
            "object_id": self.object_id,
            "object_repr": self.object_repr,
            "field_name": self.field_name,
            "old_values": serialize_audit_value(self.old_values),
            "new_values": serialize_audit_value(self.new_values),
            "reason_for_change": self.reason_for_change,
            "extra_informations": serialize_audit_value(self.extra_informations),
        }

    def _get_actor_identifier(self, request):
        if request is None:
            return None

        user = get_authenticated_user_by_request(request)
        return getattr(user, DRF_AUDIT_TRAIL_USER_PK_NAME, None)

    def _get_actor_role(self, request):
        if request is None or self.actor_type != AuditLogEntry.USER:
            return None

        user = get_authenticated_user_by_request(request)
        if user is None:
            return None

        getter = get_user_role_getter()
        if getter is None:
            return None

        return getter(user, request)


class AuditLogContext(AuditLogDraft):
    def __init__(self, content_object=None, **kwargs):
        super().__init__(content_object=content_object, **kwargs)
        self._entries = []

    def add_field_change(
        self, field_name=None, old_values=None, new_values=None, **kwargs
    ):
        entry_data = self.as_dict()
        entry_data.update(kwargs)

        if field_name is not None:
            entry_data["field_name"] = field_name
        if old_values is not None:
            entry_data["old_values"] = old_values
        if new_values is not None:
            entry_data["new_values"] = new_values

        entry = AuditLogDraft(**entry_data)
        self._entries.append(entry)
        return entry

    def as_dict(self):
        return {
            field_name: getattr(self, field_name) for field_name in self.entry_fields
        }

    def iter_entries(self):
        if self._entries:
            return iter(self._entries)
        return iter([self])


def audit_log(
    *,
    event_type,
    action_description,
    field_name=None,
    actor_type=AuditLogEntry.USER,
    actor_identifier=None,
    actor_role=None,
    content_type=None,
    object_id=None,
    object_repr=None,
    old_values=None,
    new_values=None,
    reason_for_change=None,
    extra_informations=None,
    parameter_name="audit_log",
):
    def decorator(func):
        def _build_context():
            return AuditLogContext(
                actor_identifier=actor_identifier,
                actor_role=actor_role,
                actor_type=actor_type,
                event_type=event_type,
                action_description=action_description,
                content_type=content_type,
                object_id=object_id,
                object_repr=object_repr,
                field_name=field_name,
                old_values=old_values,
                new_values=new_values,
                reason_for_change=reason_for_change,
                extra_informations=extra_informations,
            )

        def _prepare_call(args, kwargs, audit_log_context):
            request = _get_request_from_call(args, kwargs)
            if request is not None:
                add_pending_audit_log_entry(request, audit_log_context)
            if _call_accepts_parameter(func, parameter_name):
                kwargs.setdefault(parameter_name, audit_log_context)
            return request

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                audit_log_context = _build_context()
                request = _prepare_call(args, kwargs, audit_log_context)

                result = await func(*args, **kwargs)

                if request is None:
                    _persist_requestless_context(audit_log_context)

                return result

            return async_wrapper

        @wraps(func)
        def wrapper(*args, **kwargs):
            audit_log_context = _build_context()
            request = _prepare_call(args, kwargs, audit_log_context)

            result = func(*args, **kwargs)

            if request is None:
                _persist_requestless_context(audit_log_context)

            return result

        return wrapper

    return decorator


def _persist_requestless_context(audit_log_context):
    for audit_log_draft in audit_log_context.iter_entries():
        create_audit_log_entry(audit_log_draft)


def add_pending_audit_log_entry(request, audit_log_context):
    request.META.setdefault(PENDING_AUDIT_LOG_ENTRIES_KEY, []).append(audit_log_context)


def get_pending_audit_log_entries(request):
    return request.META.get(PENDING_AUDIT_LOG_ENTRIES_KEY, [])


def has_pending_audit_log_entries(request):
    return bool(get_pending_audit_log_entries(request))


def persist_pending_audit_log_entries(request, request_audit_event):
    created_entries = []

    for audit_log_context in get_pending_audit_log_entries(request):
        for audit_log_draft in audit_log_context.iter_entries():
            created_entries.append(
                create_audit_log_entry(
                    audit_log_draft,
                    request_audit_event=request_audit_event,
                    request=request,
                )
            )

    request.META[PENDING_AUDIT_LOG_ENTRIES_KEY] = []
    return created_entries


def create_audit_log_entry(audit_log_draft, request_audit_event=None, request=None):
    if not audit_log_draft.event_type:
        raise ValueError("event_type is required.")
    if not audit_log_draft.action_description:
        raise ValueError("action_description is required.")

    return AuditLogEntry.objects.create(
        **audit_log_draft.to_entry_kwargs(
            request_audit_event=request_audit_event,
            request=request,
        )
    )


def record_system_event(*, event_type: str, action_description: str, **kwargs):
    kwargs.setdefault("actor_type", AuditLogEntry.SYSTEM)
    kwargs.setdefault(
        "actor_identifier", DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_IDENTIFIER
    )
    kwargs.setdefault("actor_role", DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE)
    kwargs["event_type"] = event_type
    kwargs["action_description"] = action_description
    return create_audit_log_entry(AuditLogDraft(**kwargs))


def get_user_role_getter():
    getter = getattr(
        settings,
        "DRF_AUDIT_TRAIL_USER_ROLE_GETTER",
        DRF_AUDIT_TRAIL_USER_ROLE_GETTER,
    )
    if getter is None:
        return None
    if callable(getter):
        return getter
    return import_string(getter)


def _get_request_from_call(args, kwargs):
    request = kwargs.get("request")
    if _looks_like_request(request):
        return request

    for arg in args:
        if _looks_like_request(arg):
            return arg

        request = getattr(arg, "request", None)
        if _looks_like_request(request):
            return request

    return None


def _looks_like_request(value):
    return hasattr(value, "META") and hasattr(value, "method")


def _call_accepts_parameter(func, parameter_name):
    try:
        parameters = signature(func).parameters.values()
    except (TypeError, ValueError):
        return True

    for parameter in parameters:
        if parameter.name == parameter_name:
            return True
        if parameter.kind == Parameter.VAR_KEYWORD:
            return True

    return False
