from copy import deepcopy

from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.module_loading import import_string


def resolve_value_serializers(config, model_config):
    serializers = {
        "default": config.get("default_value_serializer", "raw"),
        "foreign_key": config.get("foreign_key_value_serializer", "repr"),
        "file": config.get("file_value_serializer", "name"),
        "image": config.get("image_value_serializer", "name"),
        "fields": deepcopy(config.get("field_value_serializers", {})),
    }

    if model_config.get("default_value_serializer") is not None:
        serializers["default"] = model_config.get("default_value_serializer")
    if model_config.get("foreign_key_value_serializer") is not None:
        serializers["foreign_key"] = model_config.get("foreign_key_value_serializer")
    if model_config.get("file_value_serializer") is not None:
        serializers["file"] = model_config.get("file_value_serializer")
    if model_config.get("image_value_serializer") is not None:
        serializers["image"] = model_config.get("image_value_serializer")

    serializers["fields"].update(model_config.get("field_value_serializers", {}))
    return serializers


def format_field_value(obj, field, raw_value, serializers):
    strategy = select_field_serializer(field, serializers)
    serializer = resolve_serializer_callable(strategy)
    return serializer(obj=obj, field=field, raw_value=raw_value)


def select_field_serializer(field, serializers):
    field_serializers = serializers.get("fields", {})
    if field.name in field_serializers:
        return field_serializers[field.name]
    if field.attname in field_serializers:
        return field_serializers[field.attname]

    if isinstance(field, models.ImageField):
        return serializers.get("image", serializers.get("file", "name"))
    if isinstance(field, models.FileField):
        return serializers.get("file", "name")
    if isinstance(field, (models.ForeignKey, models.OneToOneField)):
        return serializers.get("foreign_key", "repr")

    return serializers.get("default", "raw")


def resolve_serializer_callable(serializer):
    if callable(serializer):
        return serializer

    if not isinstance(serializer, str):
        return serialize_text

    builtin = BUILTIN_SERIALIZERS.get(serializer)
    if builtin is not None:
        return builtin

    imported = import_string(serializer)
    if callable(imported):
        return imported

    return serialize_text


def serialize_text(*, obj, field, raw_value):
    if raw_value is None:
        return None
    return str(raw_value)


def serialize_raw(*, obj, field, raw_value):
    return raw_value


def serialize_repr(*, obj, field, raw_value):
    if raw_value is None:
        return None

    related = get_related_instance(obj, field)
    if related is not None:
        return str(related)

    return str(raw_value)


def serialize_pk(*, obj, field, raw_value):
    if raw_value is None:
        return None
    return str(raw_value)


def serialize_pk_and_repr(*, obj, field, raw_value):
    if raw_value is None:
        return None

    related = get_related_instance(obj, field)
    return {
        "pk": str(raw_value),
        "repr": str(related) if related is not None else str(raw_value),
    }


def serialize_file_name(*, obj, field, raw_value):
    if raw_value is None:
        return None

    file_value = get_file_value(obj, field)
    if file_value is not None:
        return file_value.name
    return str(raw_value)


def serialize_file_path(*, obj, field, raw_value):
    if raw_value is None:
        return None

    file_value = get_file_value(obj, field)
    if file_value is not None:
        path = safe_file_path(file_value)
        if path:
            return path
        if file_value.name:
            return file_value.name

    return str(raw_value)


def serialize_file_name_and_path(*, obj, field, raw_value):
    if raw_value is None:
        return None

    file_value = get_file_value(obj, field)
    if file_value is not None:
        return {
            "name": file_value.name,
            "path": safe_file_path(file_value),
        }

    return {
        "name": str(raw_value),
        "path": None,
    }


def get_related_instance(obj, field):
    if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
        return None

    try:
        return getattr(obj, field.name)
    except (ObjectDoesNotExist, AttributeError):
        return None


def get_file_value(obj, field):
    if not isinstance(field, models.FileField):
        return None

    try:
        value = getattr(obj, field.name)
    except AttributeError:
        return None

    if not value:
        return None
    return value


def safe_file_path(file_value):
    try:
        return file_value.path
    except (ValueError, NotImplementedError, AttributeError):
        return None


BUILTIN_SERIALIZERS = {
    "text": serialize_text,
    "raw": serialize_raw,
    "repr": serialize_repr,
    "pk": serialize_pk,
    "pk_and_repr": serialize_pk_and_repr,
    "name": serialize_file_name,
    "path": serialize_file_path,
    "name_and_path": serialize_file_name_and_path,
}
