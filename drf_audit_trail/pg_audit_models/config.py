from copy import deepcopy

from django.apps import apps
from django.conf import settings
from django.db.models import Model

from drf_audit_trail.settings import DEFAULT_DRF_AUDIT_TRAIL_PG_AUDIT

ALL_MODELS = "__all__"
INTERNAL_EXCLUDED_APP_REFERENCES = frozenset(
    ("pg_audit_models", "drf_audit_trail.pg_audit_models")
)


def get_pg_audit_config():
    config = deepcopy(DEFAULT_DRF_AUDIT_TRAIL_PG_AUDIT)
    config.update(getattr(settings, "DRF_AUDIT_TRAIL_PG_AUDIT", {}) or {})
    return config


def get_configured_model_references(config=None):
    config = config or get_pg_audit_config()
    configured_models = config.get("models")

    if configured_models == ALL_MODELS:
        return ALL_MODELS

    if isinstance(configured_models, (str, type)) or isinstance(
        configured_models, Model
    ):
        return (configured_models,)

    return tuple(configured_models or ())


def get_audited_models(config=None):
    config = config or get_pg_audit_config()
    model_references = get_configured_model_references(config)
    if config.get("audit_all_models") or model_references == ALL_MODELS:
        return tuple(
            model for model in apps.get_models() if not is_model_excluded(model, config)
        )

    if not model_references:
        return ()

    return tuple(
        model
        for model in apps.get_models()
        if not is_model_excluded(model, config)
        and model_matches_any_reference(model, model_references)
    )


def get_audited_model_tables(config=None):
    config = config or get_pg_audit_config()
    tables = {model._meta.db_table for model in get_audited_models(config)}

    model_references = get_configured_model_references(config)
    if model_references not in ((), ALL_MODELS) and not config.get("audit_all_models"):
        known_model_references = {
            identifier
            for model in apps.get_models()
            for identifier in get_model_identifiers(model)
        }
        for reference in model_references:
            reference_value = get_reference_value(reference)
            if reference_value and reference_value not in known_model_references:
                tables.add(reference_value)

    excluded_tables = {
        model._meta.db_table
        for model in apps.get_models()
        if is_model_excluded(model, config)
    }
    tables.difference_update(excluded_tables)
    return tuple(sorted(tables))


def is_model_audited(model, config=None):
    config = config or get_pg_audit_config()
    if is_model_excluded(model, config):
        return False

    model_references = get_configured_model_references(config)
    if config.get("audit_all_models") or model_references == ALL_MODELS:
        return True

    return bool(model_references) and model_matches_any_reference(
        model, model_references
    )


def is_model_excluded(model, config=None):
    config = config or get_pg_audit_config()
    app_references = set(config.get("excluded_apps") or ())
    app_references.update(INTERNAL_EXCLUDED_APP_REFERENCES)
    model_app_config = model._meta.app_config

    if (
        model._meta.app_label in app_references
        or model_app_config.name in app_references
    ):
        return True

    return model_matches_any_reference(model, config.get("excluded_models") or ())


def model_matches_any_reference(model, references):
    return any(model_matches_reference(model, reference) for reference in references)


def model_matches_reference(model, reference):
    reference_value = get_reference_value(reference)
    if not reference_value:
        return False

    return reference_value in get_model_identifiers(model)


def get_model_identifiers(model):
    return {
        model._meta.db_table,
        model._meta.label,
        model._meta.label_lower,
        model.__name__,
        model.__name__.lower(),
    }


def get_reference_value(reference):
    if isinstance(reference, str):
        return reference
    if isinstance(reference, type) and issubclass(reference, Model):
        return reference._meta.label
    if isinstance(reference, Model):
        return reference._meta.label
    return str(reference) if reference is not None else None


def get_module_paths(config, modules_key, suffixes_key):
    module_paths = list(config.get(modules_key) or ())
    suffixes = tuple(config.get(suffixes_key) or ())

    for app_config in apps.get_app_configs():
        for suffix in suffixes:
            module_paths.append(f"{app_config.name}.{suffix}")

    return tuple(dict.fromkeys(module_paths))


def get_api_views_module_paths(config=None):
    config = config or get_pg_audit_config()
    return get_module_paths(
        config,
        "api_views_modules",
        "api_views_module_suffixes",
    )


def get_django_views_module_paths(config=None):
    config = config or get_pg_audit_config()
    return get_module_paths(
        config,
        "django_views_modules",
        "django_views_module_suffixes",
    )
