from copy import deepcopy
from inspect import Parameter, signature

from django.db import transaction

from drf_audit_trail.audit_log import (
    AuditLogDraft,
    add_pending_audit_log_entry,
    create_audit_log_entry,
)

from .context import disable_manager_audit
from .snapshots import snapshot_object_identity
from .utils import get_model_label


def schedule_create_entries(objs, audit_plan, using):
    snapshots = {
        obj.pk: snapshot_object_identity(obj) for obj in objs if obj.pk is not None
    }
    drafts = []
    for snapshot in snapshots.values():
        drafts.append(
            build_draft(
                audit_plan,
                snapshot,
                field_name=None,
                old_value=None,
                new_value=None,
                old_raw_value=None,
                new_raw_value=None,
                before_snapshot=None,
                after_snapshot=snapshot,
            )
        )
    schedule_drafts(drafts, audit_plan, using)


def schedule_update_entries(before, after, audit_plan, using):
    drafts = []
    for pk, before_snapshot in before.items():
        after_snapshot = after.get(pk)
        if not after_snapshot:
            continue
        for field_name in before_snapshot["values"]:
            old_value = before_snapshot["values"].get(field_name)
            new_value = after_snapshot["values"].get(field_name)
            old_raw, old_display = extract_raw_and_display(old_value)
            new_raw, new_display = extract_raw_and_display(new_value)

            if old_raw == new_raw:
                continue
            drafts.append(
                build_draft(
                    audit_plan,
                    after_snapshot,
                    field_name=field_name,
                    old_value=old_display,
                    new_value=new_display,
                    old_raw_value=old_raw,
                    new_raw_value=new_raw,
                    before_snapshot=before_snapshot,
                    after_snapshot=after_snapshot,
                )
            )
    schedule_drafts(drafts, audit_plan, using)


def extract_raw_and_display(value):
    if isinstance(value, dict) and "raw" in value and "display" in value:
        return value["raw"], value["display"]
    return value, value


def schedule_delete_entries(before, audit_plan, using):
    drafts = []
    for snapshot in before.values():
        drafts.append(
            build_draft(
                audit_plan,
                snapshot,
                field_name=None,
                old_value=None,
                new_value=None,
                old_raw_value=None,
                new_raw_value=None,
                before_snapshot=snapshot,
                after_snapshot=None,
            )
        )
    schedule_drafts(drafts, audit_plan, using)


def build_draft(
    audit_plan,
    snapshot,
    *,
    field_name,
    old_value,
    new_value,
    old_raw_value,
    new_raw_value,
    before_snapshot,
    after_snapshot,
):
    model = audit_plan.model
    model_label = get_model_label(model)
    old_values = None if audit_plan.action == "create" else old_value
    new_values = None if audit_plan.action == "delete" else new_value
    extra_informations = resolve_extra_informations(
        audit_plan,
        snapshot,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        old_raw_value=old_raw_value,
        new_raw_value=new_raw_value,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )

    return AuditLogDraft(
        actor_identifier=audit_plan.actor_identifier,
        actor_role=audit_plan.actor_role,
        actor_type=audit_plan.actor_type,
        event_type=audit_plan.action.title(),
        action_description=get_action_description(audit_plan, field_name),
        content_type=model_label.lower(),
        object_id=str(snapshot["pk"]),
        object_repr=snapshot["object_repr"],
        field_name=field_name,
        old_values=old_values,
        new_values=new_values,
        reason_for_change=resolve_reason_for_entry(audit_plan, field_name),
        extra_informations=extra_informations,
    )


def resolve_reason_for_entry(audit_plan, field_name):
    reason = audit_plan.reason_for_change
    if reason in (None, ""):
        return None

    if isinstance(reason, dict):
        if not field_name:
            return None
        return reason.get(field_name)

    if audit_plan.reason_source == "request" and not field_name:
        return None

    return reason


def resolve_extra_informations(
    audit_plan,
    snapshot,
    *,
    field_name,
    old_value,
    new_value,
    old_raw_value,
    new_raw_value,
    before_snapshot,
    after_snapshot,
):
    getter_value = None
    if audit_plan.extra_informations_getter:
        getter_value = call_extra_informations_getter(
            audit_plan.extra_informations_getter,
            {
                "instance": snapshot.get("instance"),
                "model": audit_plan.model,
                "action": audit_plan.action,
                "request": audit_plan.request,
                "request_audit_event": audit_plan.request_audit_event,
                "field_name": field_name,
                "old_value": old_value,
                "new_value": new_value,
                "old_raw_value": old_raw_value,
                "new_raw_value": new_raw_value,
                "old_values": snapshot_raw_values(before_snapshot),
                "new_values": snapshot_raw_values(after_snapshot),
            },
        )
    return merge_extra_informations(getter_value, audit_plan.extra_informations)


def call_extra_informations_getter(getter, kwargs):
    try:
        getter_signature = signature(getter)
    except (TypeError, ValueError):
        return getter(**kwargs)

    if any(
        parameter.kind == Parameter.VAR_KEYWORD
        for parameter in getter_signature.parameters.values()
    ):
        return getter(**kwargs)

    accepted_kwargs = {
        name: value
        for name, value in kwargs.items()
        if name in getter_signature.parameters
    }
    return getter(**accepted_kwargs)


def snapshot_raw_values(snapshot):
    if not snapshot:
        return None

    values = snapshot.get("values")
    if not values:
        return None

    return {
        field_name: extract_raw_and_display(value)[0]
        for field_name, value in values.items()
    }


def merge_extra_informations(getter_value, context_value):
    if context_value in (None, ""):
        return getter_value
    if getter_value in (None, ""):
        return context_value
    if isinstance(getter_value, dict) and isinstance(context_value, dict):
        merged_value = deepcopy(getter_value)
        merged_value.update(context_value)
        return merged_value
    return context_value


def get_action_description(audit_plan, field_name):
    if audit_plan.action == "update" and field_name:
        context_description = audit_plan.context_action_description
        if context_description not in (None, ""):
            return context_description

        field_description = audit_plan.field_update_action_descriptions.get(field_name)
        if field_description not in (None, ""):
            return field_description

    return (
        audit_plan.action_descriptions.get(audit_plan.action)
        or f"{audit_plan.action.title()} object"
    )


def schedule_drafts(drafts, audit_plan, using):
    if not drafts:
        return

    request = audit_plan.request
    request_audit_event = audit_plan.request_audit_event

    def persist_or_enqueue_entries():
        if request is not None and request_audit_event is None:
            add_pending_audit_log_entry(request, PendingAuditDrafts(drafts))
            return

        with disable_manager_audit():
            for draft in drafts:
                create_audit_log_entry(
                    draft,
                    request_audit_event=request_audit_event,
                    request=request,
                )

    transaction.on_commit(persist_or_enqueue_entries, using=using)


class PendingAuditDrafts:
    def __init__(self, drafts):
        self._drafts = drafts

    def iter_entries(self):
        return iter(self._drafts)
