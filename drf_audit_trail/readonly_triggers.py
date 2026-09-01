import logging

from django.apps import apps as django_apps
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.utils import DatabaseError
from django.utils.connection import ConnectionDoesNotExist

logger = logging.getLogger(__name__)

PROTECT_FUNCTION_NAME = "audit_readonly_protect"
TRIGGER_OPERATIONS = ("UPDATE", "DELETE")

CREATE_PROTECT_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {PROTECT_FUNCTION_NAME}()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Audit table "%" is read-only. Operation % is not allowed.',
        TG_TABLE_NAME, TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


def sync_readonly_triggers(
    model_specs,
    using=DEFAULT_DB_ALIAS,
    log_scope="audit",
):
    try:
        db_connection = connections[using]
    except ConnectionDoesNotExist:
        return None

    if db_connection.vendor != "postgresql":
        return None

    audit_tables = get_existing_readonly_tables(
        db_connection,
        model_specs,
        log_scope=log_scope,
    )
    if not audit_tables:
        return None

    with db_connection.cursor() as cursor:
        cursor.execute(CREATE_PROTECT_FUNCTION_SQL)
        for model_name, table_name in audit_tables:
            for operation in TRIGGER_OPERATIONS:
                trigger_name = get_trigger_name(model_name, operation)
                cursor.execute(
                    build_drop_trigger_sql(db_connection, table_name, trigger_name)
                )
                cursor.execute(
                    build_create_trigger_sql(
                        db_connection,
                        table_name,
                        trigger_name,
                        operation,
                    )
                )

    return {
        "database_alias": using,
        "database_vendor": db_connection.vendor,
        "protected_tables": tuple(table_name for _, table_name in audit_tables),
    }


def get_existing_readonly_tables(db_connection, model_specs, log_scope="audit"):
    try:
        existing_table_names = set(db_connection.introspection.table_names())
    except DatabaseError as exc:
        logger.warning(
            "Skipping %s readonly trigger sync because the database schema "
            "could not be inspected: %s",
            log_scope,
            exc,
        )
        return ()

    return tuple(
        (model_name, table_name)
        for model_name, table_name in get_model_table_names(model_specs)
        if table_name in existing_table_names
    )


def get_model_table_names(model_specs):
    table_names = []
    for app_label, model_name in model_specs:
        try:
            model = django_apps.get_model(app_label, model_name)
        except LookupError:
            continue

        table_names.append((model_name, model._meta.db_table))
    return tuple(table_names)


def get_trigger_name(model_name, operation):
    return f"trg_{model_name.lower()}_no_{operation.lower()}"


def build_drop_trigger_sql(db_connection, table_name, trigger_name):
    return (
        "DROP TRIGGER IF EXISTS "
        f"{db_connection.ops.quote_name(trigger_name)} "
        f"ON {db_connection.ops.quote_name(table_name)};"
    )


def build_create_trigger_sql(db_connection, table_name, trigger_name, operation):
    return (
        "CREATE TRIGGER "
        f"{db_connection.ops.quote_name(trigger_name)} "
        f"BEFORE {operation} "
        f"ON {db_connection.ops.quote_name(table_name)} "
        "FOR EACH ROW "
        f"EXECUTE FUNCTION {db_connection.ops.quote_name(PROTECT_FUNCTION_NAME)}();"
    )
