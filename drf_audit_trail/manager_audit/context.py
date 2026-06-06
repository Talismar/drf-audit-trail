from contextlib import contextmanager
from contextvars import ContextVar

from .constants import _UNSET
from .utils import (
    copy_context,
    merge_model_overrides,
    merge_model_references,
)


_AUDIT_CONTEXT = ContextVar("drf_audit_trail_manager_audit_context", default={})


def get_current_audit_context():
    return copy_context(_AUDIT_CONTEXT.get({}))


@contextmanager
def audit_model_context(
    *,
    request=None,
    request_audit_event=None,
    reason_for_change=_UNSET,
    actor_identifier=_UNSET,
    actor_role=_UNSET,
    actor_type=_UNSET,
    action_description=None,
    model=None,
    models=None,
    fields=_UNSET,
    exclude_fields=_UNSET,
    extra_informations=_UNSET,
):
    """
    Temporarily enables and customizes model-level audit.

    Pass ``model=MyModel`` or ``model=instance`` to audit a model without
    writing a ``models={...}`` config block. When no fields are configured for
    that model, the package default fields are used.
    """
    context = get_current_audit_context()

    if request is not None:
        context["request"] = request
    if request_audit_event is not None:
        context["request_audit_event"] = request_audit_event
    if reason_for_change is not _UNSET:
        context["reason_for_change"] = reason_for_change
    if actor_identifier is not _UNSET:
        context["actor_identifier"] = actor_identifier
    if actor_role is not _UNSET:
        context["actor_role"] = actor_role
    if actor_type is not _UNSET:
        context["actor_type"] = actor_type
    if extra_informations is not _UNSET:
        context["extra_informations"] = extra_informations

    if action_description:
        context["action_description"] = action_description
    if model is not None:
        merge_model_references(
            context.setdefault("models", {}),
            model,
            fields=fields,
            exclude_fields=exclude_fields,
        )
    if models:
        if isinstance(models, dict):
            merge_model_overrides(context.setdefault("models", {}), models)
        else:
            merge_model_references(
                context.setdefault("models", {}),
                models,
                fields=fields,
                exclude_fields=exclude_fields,
            )

    token = _AUDIT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _AUDIT_CONTEXT.reset(token)


def set_audit_reason(reason):
    context = get_current_audit_context()
    context["reason_for_change"] = reason
    _AUDIT_CONTEXT.set(context)


@contextmanager
def disable_manager_audit():
    context = get_current_audit_context()
    context["disabled"] = True
    token = _AUDIT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _AUDIT_CONTEXT.reset(token)
