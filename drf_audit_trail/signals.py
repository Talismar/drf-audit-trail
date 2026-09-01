from django.db import DEFAULT_DB_ALIAS
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from drf_audit_trail.readonly_triggers import (
    get_model_table_names,
    sync_readonly_triggers,
)

AUDIT_MODEL_NAMES = (
    "LoginAuditEvent",
    "RequestAuditEvent",
)
AUDIT_MODEL_SPECS = tuple(
    ("drf_audit_trail", model_name) for model_name in AUDIT_MODEL_NAMES
)

_configured_database_aliases = set()


def sync_audit_readonly_triggers(using=DEFAULT_DB_ALIAS):
    return sync_readonly_triggers(
        AUDIT_MODEL_SPECS,
        using=using,
        log_scope="audit",
    )


def get_audit_model_table_names():
    return get_model_table_names(AUDIT_MODEL_SPECS)


@receiver(post_migrate)
def run_audit_readonly_triggers_sync(sender, *args, **kwargs):
    using = kwargs.get("using") or DEFAULT_DB_ALIAS
    if using in _configured_database_aliases:
        return

    status = sync_audit_readonly_triggers(using=using)
    if status is not None:
        _configured_database_aliases.add(using)
