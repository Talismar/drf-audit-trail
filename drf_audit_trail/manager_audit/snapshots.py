from copy import copy

from .formatting import format_field_value


def snapshot_queryset(queryset, audit_plan, fields=None):
    if fields is None:
        fields = audit_plan.fields
    snapshots = {}
    for obj in queryset:
        snapshots[obj.pk] = snapshot_object(obj, fields, audit_plan)
    return snapshots


def snapshot_queryset_identity(queryset):
    snapshots = {}
    for obj in queryset:
        snapshots[obj.pk] = snapshot_object_identity(obj)
    return snapshots


def snapshot_by_pks(model, pks, audit_plan, using, fields=None):
    if fields is None:
        fields = audit_plan.fields
    if not pks:
        return {}
    queryset = model._base_manager.using(using).filter(pk__in=pks)
    return snapshot_queryset(queryset, audit_plan, fields=fields)


def snapshot_existing_for_update_or_create(
    model,
    lookup_kwargs,
    audit_plan,
    using,
    fields=None,
):
    try:
        obj = model._base_manager.using(using).get(**lookup_kwargs)
    except model.DoesNotExist:
        return {}
    return {obj.pk: snapshot_object(obj, fields or audit_plan.fields, audit_plan)}


def snapshot_object(obj, fields, audit_plan):
    snapshot = snapshot_object_identity(obj)
    values = {}
    for field_name in fields:
        raw_value = get_field_value(obj, field_name)
        field = obj._meta.get_field(field_name)
        formatted_value = format_field_value(
            obj,
            field,
            raw_value,
            audit_plan.value_serializers,
        )
        values[field_name] = {
            "raw": raw_value,
            "display": formatted_value,
        }
    snapshot["values"] = values
    return snapshot


def snapshot_object_identity(obj):
    return {
        "pk": obj.pk,
        "object_repr": str(obj),
        "instance": copy(obj),
    }


def get_field_value(obj, field_name):
    field = obj._meta.get_field(field_name)
    return getattr(obj, field.attname)
