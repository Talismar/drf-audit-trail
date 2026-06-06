from copy import deepcopy

from django.db import models

from .constants import _UNSET


def get_model_label(model):
    return f"{model._meta.app_label}.{model._meta.object_name}"


def get_model_label_from_reference(model_ref):
    if isinstance(model_ref, str):
        return model_ref

    if isinstance(model_ref, models.Model):
        return get_model_label(model_ref.__class__)

    if isinstance(model_ref, type) and issubclass(model_ref, models.Model):
        return get_model_label(model_ref)

    if isinstance(model_ref, models.QuerySet):
        return get_model_label(model_ref.model)

    referenced_model = getattr(model_ref, "model", None)
    if isinstance(referenced_model, type) and issubclass(
        referenced_model,
        models.Model,
    ):
        return get_model_label(referenced_model)

    raise TypeError(
        "audit_model_context model references must be Django model classes, "
        "model instances, querysets, managers, or model labels."
    )


def has_model_config(model, model_configs):
    if not model_configs:
        return False

    model_label = get_model_label(model)
    return model_label in model_configs or model_label.lower() in model_configs


def get_model_field_names(model):
    return {field.name for field in model._meta.concrete_fields} | {
        field.attname for field in model._meta.concrete_fields
    }


def get_instance_db(obj):
    return obj._state.db or "default"


def get_save_db(obj, kwargs):
    return kwargs.get("using") or obj._state.db or "default"


def normalize_updated_field_names(model, updated_fields):
    field_map = {}
    for field in model._meta.concrete_fields:
        field_map[field.name] = field.name
        field_map[field.attname] = field.name
    return {field_map.get(field_name, field_name) for field_name in updated_fields}


def deep_merge_dict(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge_dict(target[key], value)
        else:
            target[key] = deepcopy(value)


def merge_model_overrides(target, source):
    for model_label, model_config in source.items():
        target.setdefault(model_label, {})
        deep_merge_dict(target[model_label], model_config)


def merge_model_references(
    target,
    model_refs,
    *,
    fields=_UNSET,
    exclude_fields=_UNSET,
):
    model_config = {}
    if fields is not _UNSET:
        model_config["fields"] = fields
    if exclude_fields is not _UNSET:
        model_config["exclude_fields"] = exclude_fields

    if isinstance(model_refs, (list, tuple, set, frozenset)):
        references = model_refs
    else:
        references = [model_refs]

    for model_ref in references:
        model_label = get_model_label_from_reference(model_ref)
        target.setdefault(model_label, {})
        if model_config:
            deep_merge_dict(target[model_label], model_config)


def copy_context(context):
    copied = {}
    for key, value in context.items():
        if key in {"request", "request_audit_event"}:
            copied[key] = value
        else:
            copied[key] = deepcopy(value)
    return copied
