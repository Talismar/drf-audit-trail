import json
from collections.abc import Mapping
from copy import deepcopy

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.module_loading import import_string

from drf_audit_trail.models import AuditLogEntry
from drf_audit_trail.settings import DEFAULT_DRF_AUDIT_TRAIL_MANAGER_AUDIT

from .context import get_current_audit_context
from .formatting import resolve_value_serializers
from .utils import (
    deep_merge_dict,
    get_model_field_names,
    get_model_label,
    has_model_config,
    normalize_updated_field_names,
)


class AuditPlan:
    def __init__(
        self,
        *,
        enabled,
        model,
        action,
        fields=None,
        require_reason=False,
        reason_for_change=None,
        reason_source=None,
        reason_field=None,
        action_descriptions=None,
        context_action_description=None,
        field_update_action_descriptions=None,
        actor_identifier=None,
        actor_role=None,
        actor_type=None,
        request=None,
        request_audit_event=None,
        extra_informations=None,
        extra_informations_getter=None,
        cleaned_write_kwargs=None,
        value_serializers=None,
    ):
        self.enabled = enabled
        self.model = model
        self.action = action
        self.fields = fields or []
        self.require_reason = require_reason
        self.reason_for_change = reason_for_change
        self.reason_source = reason_source
        self.reason_field = reason_field
        self.action_descriptions = action_descriptions or {}
        self.context_action_description = context_action_description
        self.field_update_action_descriptions = field_update_action_descriptions or {}
        self.actor_identifier = actor_identifier
        self.actor_role = actor_role
        self.actor_type = actor_type
        self.request = request
        self.request_audit_event = request_audit_event
        self.extra_informations = extra_informations
        self.extra_informations_getter = extra_informations_getter
        self.cleaned_write_kwargs = cleaned_write_kwargs or {}
        self.value_serializers = value_serializers or {}

    def with_action(self, action):
        return AuditPlan(
            enabled=self.enabled,
            model=self.model,
            action=action,
            fields=self.fields,
            require_reason=self.require_reason,
            reason_for_change=self.reason_for_change,
            reason_source=self.reason_source,
            reason_field=self.reason_field,
            action_descriptions=self.action_descriptions,
            context_action_description=self.context_action_description,
            field_update_action_descriptions=self.field_update_action_descriptions,
            actor_identifier=self.actor_identifier,
            actor_role=self.actor_role,
            actor_type=self.actor_type,
            request=self.request,
            request_audit_event=self.request_audit_event,
            extra_informations=self.extra_informations,
            extra_informations_getter=self.extra_informations_getter,
            cleaned_write_kwargs=self.cleaned_write_kwargs,
            value_serializers=self.value_serializers,
        )


def build_audit_plan(
    model,
    *,
    action,
    write_kwargs=None,
    mutate_write_kwargs=True,
):
    context = get_current_audit_context()
    config = get_manager_audit_config()
    model_config = resolve_model_config(model, config, context)

    cleaned_write_kwargs = (write_kwargs or {}).copy()
    if not is_model_audited(model, config, context, model_config):
        return AuditPlan(
            enabled=False,
            model=model,
            action=action,
            cleaned_write_kwargs=write_kwargs or {},
        )

    reason_field = model_config.get("reason_field") or "reason_for_change"
    reason_from_kwargs = extract_reason_from_write_kwargs(
        model,
        cleaned_write_kwargs,
        reason_field,
        mutate=mutate_write_kwargs,
    )
    reason, reason_source = resolve_reason(
        context,
        config,
        model_config,
        reason_from_kwargs,
    )

    action_descriptions = deepcopy(config.get("default_action_descriptions", {}))
    action_descriptions.update(model_config.get("action_descriptions", {}))
    context_action_description = context.get("action_description")
    if context_action_description not in (None, ""):
        action_descriptions[action] = context_action_description

    return AuditPlan(
        enabled=True,
        model=model,
        action=action,
        fields=get_tracked_field_names(model, config, model_config),
        require_reason=bool(model_config.get("require_reason")),
        reason_for_change=reason,
        reason_source=reason_source,
        reason_field=reason_field,
        action_descriptions=action_descriptions,
        context_action_description=context_action_description,
        field_update_action_descriptions=get_field_update_action_descriptions(model),
        actor_identifier=context.get("actor_identifier"),
        actor_role=context.get("actor_role"),
        actor_type=context.get("actor_type") or AuditLogEntry.USER,
        request=context.get("request"),
        request_audit_event=context.get("request_audit_event"),
        extra_informations=context.get("extra_informations"),
        extra_informations_getter=resolve_extra_informations_getter(
            config,
            model_config,
        ),
        cleaned_write_kwargs=cleaned_write_kwargs,
        value_serializers=resolve_value_serializers(config, model_config),
    )


def get_manager_audit_config():
    user_config = getattr(
        settings,
        "DRF_AUDIT_TRAIL_MANAGER_AUDIT",
        DEFAULT_DRF_AUDIT_TRAIL_MANAGER_AUDIT,
    )
    config = deepcopy(DEFAULT_DRF_AUDIT_TRAIL_MANAGER_AUDIT)
    deep_merge_dict(config, user_config or {})
    return config


def resolve_model_config(model, config, context):
    model_label = get_model_label(model)
    model_config = {}
    model_config.update(config.get("models", {}).get(model_label, {}))
    model_config.update(config.get("models", {}).get(model_label.lower(), {}))
    model_config.update(context.get("models", {}).get(model_label, {}))
    model_config.update(context.get("models", {}).get(model_label.lower(), {}))
    return model_config


def is_model_audited(model, config, context, model_config):
    if context.get("disabled") or not config.get("enabled", True):
        return False
    if model._meta.app_label in config.get("excluded_apps", []):
        return False
    if model_config:
        return True
    if has_model_config(model, config.get("models", {})):
        return True
    if has_model_config(model, context.get("models", {})):
        return True
    return uses_audited_manager(model)


def uses_audited_manager(model):
    from .managers import AuditedManager

    return isinstance(model._default_manager, AuditedManager) or isinstance(
        model._base_manager,
        AuditedManager,
    )


def get_field_update_action_descriptions(model):
    descriptions = getattr(model, "FIELD_UPDATE_ACTION_DESCRIPTIONS", None)
    if isinstance(descriptions, Mapping):
        return dict(descriptions)
    return {}


def resolve_reason(context, config, model_config, reason_from_kwargs):
    if context.get("reason_for_change") not in (None, ""):
        return context.get("reason_for_change"), "context"
    if reason_from_kwargs not in (None, ""):
        return reason_from_kwargs, "kwargs"

    request_reason = get_request_reason_for_change(
        context.get("request"),
        config.get("reason_for_change_key"),
    )
    if request_reason not in (None, ""):
        return request_reason, "request"

    getter = model_config.get("reason_getter") or config.get("default_reason_getter")
    if getter:
        getter = import_string(getter) if isinstance(getter, str) else getter
        reason = getter(context)
        if reason not in (None, ""):
            return reason, "getter"

    if model_config.get("default_reason") not in (None, ""):
        return model_config.get("default_reason"), "default"
    return config.get("default_reason"), "default"


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


def resolve_extra_informations_getter(config, model_config):
    getter = model_config.get("extra_informations_getter") or config.get(
        "default_extra_informations_getter"
    )
    if isinstance(getter, str):
        return import_string(getter)
    return getter


def extract_reason_from_write_kwargs(model, write_kwargs, reason_field, *, mutate):
    if not reason_field or reason_field not in write_kwargs:
        return None
    if reason_field in get_model_field_names(model):
        return write_kwargs.get(reason_field)
    if mutate:
        return write_kwargs.pop(reason_field)
    return write_kwargs.get(reason_field)


def remove_reason_from_get_or_create_kwargs(model, kwargs, defaults, reason_field):
    kwargs = kwargs.copy()
    defaults = defaults.copy() if defaults else {}
    if reason_field not in get_model_field_names(model):
        kwargs.pop(reason_field, None)
        defaults.pop(reason_field, None)
    return kwargs, defaults


def get_tracked_field_names(model, config, model_config):
    configured_fields = model_config.get("fields", config.get("default_fields"))
    excluded_fields = set(config.get("default_exclude_fields", []))
    excluded_fields.update(model_config.get("exclude_fields", []))

    concrete_fields = []
    for field in model._meta.concrete_fields:
        if field.primary_key:
            continue
        if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
            continue
        if field.name in excluded_fields or field.attname in excluded_fields:
            continue
        concrete_fields.append(field.name)

    if configured_fields == "__all__":
        return concrete_fields

    return [
        field_name
        for field_name in configured_fields or []
        if field_name in concrete_fields and field_name not in excluded_fields
    ]


def get_updated_tracked_fields(audit_plan, updated_fields):
    updated_fields = normalize_updated_field_names(audit_plan.model, updated_fields)
    return [field for field in audit_plan.fields if field in updated_fields]


def validate_required_reason(audit_plan):
    if audit_plan.require_reason and not audit_plan.reason_for_change:
        raise ValidationError("reason_for_change is required for audited changes.")
