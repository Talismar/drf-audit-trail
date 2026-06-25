import logging
import sys

from django.apps import apps as django_apps
from django.core.signals import request_started
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate
from django.db.utils import DatabaseError
from django.dispatch import receiver
from django.utils.connection import ConnectionDoesNotExist

from .config import get_audited_model_tables, get_pg_audit_config

logger = logging.getLogger(__name__)

STARTUP_SYNC_SKIPPED_COMMANDS = frozenset(
    (
        "check",
        "collectstatic",
        "compilemessages",
        "makemessages",
        "makemigrations",
        "migrate",
        "showmigrations",
        "sqlmigrate",
        "sync_pg_audit_triggers",
        "test",
    )
)

CREATE_TRIGGERS_SQL_TEMPLATE = """
DO
$$
DECLARE
    t RECORD;
    v_audited_tables TEXT[] := {audited_model_values};
BEGIN
    FOR t IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename = ANY (v_audited_tables)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.triggers
            WHERE trigger_name = CONCAT('trg_log_update_', t.tablename)
              AND event_object_schema = 'public'
              AND event_object_table = t.tablename
        ) THEN
            EXECUTE format(
            '
                    CREATE TRIGGER %I
                    AFTER INSERT OR UPDATE OR DELETE ON %I
                    FOR EACH ROW
                    EXECUTE FUNCTION fn_log_update();
            ',
            CONCAT('trg_log_update_', t.tablename),
            t.tablename
            );
        END IF;
    END LOOP;

    FOR t IN
        SELECT event_object_table AS tablename
        FROM information_schema.triggers
        WHERE trigger_schema = 'public'
          AND event_object_schema = 'public'
          AND trigger_name LIKE 'trg_log_update_%'
          AND NOT (event_object_table = ANY (v_audited_tables))
        GROUP BY event_object_table
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS %I ON %I;',
            CONCAT('trg_log_update_', t.tablename),
            t.tablename
        );
    END LOOP;
END;
$$;
"""

_configured_database_aliases = set()
_startup_synced_database_aliases = set()


def should_sync_pg_audit_triggers_on_start(argv=None):
    argv = tuple(sys.argv if argv is None else argv)
    if len(argv) > 1 and argv[1] in STARTUP_SYNC_SKIPPED_COMMANDS:
        return False
    return True


def is_pg_audit_database_ready(using=DEFAULT_DB_ALIAS):
    try:
        db_connection = connections[using]
    except ConnectionDoesNotExist:
        return False

    if db_connection.vendor != "postgresql":
        return False

    try:
        with db_connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    to_regclass('public.pg_audit_models_actionlog') IS NOT NULL
                    AND to_regclass('public.pg_audit_models_difflog') IS NOT NULL
                    AND EXISTS (
                        SELECT 1
                        FROM pg_proc
                        JOIN pg_namespace ON pg_namespace.oid = pg_proc.pronamespace
                        WHERE pg_namespace.nspname = 'public'
                          AND pg_proc.proname = 'fn_log_update'
                    )
                """)
            return bool(cursor.fetchone()[0])
    except DatabaseError as exc:
        logger.warning(
            "Skipping pg_audit_models trigger sync on startup because the audit "
            "schema is not ready: %s",
            exc,
        )
        return False


def sync_pg_audit_triggers_on_start(using=DEFAULT_DB_ALIAS, argv=None):
    if not django_apps.ready:
        return None

    if not should_sync_pg_audit_triggers_on_start(argv):
        return None

    if using in _startup_synced_database_aliases:
        return None

    try:
        if not is_pg_audit_database_ready(using):
            return None

        status = sync_pg_audit_triggers(using=using)
    except Exception as exc:
        logger.warning(
            "Unable to sync pg_audit_models triggers on startup: %s",
            exc,
            exc_info=True,
        )
        return None

    _startup_synced_database_aliases.add(using)
    return status


@receiver(request_started)
def run_pg_audit_startup_sync_on_request(sender, **kwargs):
    sync_pg_audit_triggers_on_start()


@receiver(connection_created)
def run_pg_audit_startup_sync_on_connection(sender, connection, **kwargs):
    sync_pg_audit_triggers_on_start(using=connection.alias)


def get_pg_audit_trigger_status(using=DEFAULT_DB_ALIAS, audited_model_tables=None):
    db_connection = connections[using]
    audited_model_tables = tuple(
        audited_model_tables
        if audited_model_tables is not None
        else get_audited_model_tables(get_pg_audit_config())
    )
    status = {
        "database_alias": using,
        "database_vendor": db_connection.vendor,
        "audited_tables": audited_model_tables,
        "triggered_tables": (),
        "missing_tables": audited_model_tables,
    }

    if db_connection.vendor != "postgresql":
        return status

    with db_connection.cursor() as cursor:
        cursor.execute("""
            SELECT event_object_table
            FROM information_schema.triggers
            WHERE trigger_schema = 'public'
              AND event_object_schema = 'public'
              AND trigger_name LIKE 'trg_log_update_%'
            GROUP BY event_object_table
            ORDER BY event_object_table
            """)
        triggered_tables = tuple(row[0] for row in cursor.fetchall())

    triggered_table_set = set(triggered_tables)
    status["triggered_tables"] = triggered_tables
    status["missing_tables"] = tuple(
        table_name
        for table_name in audited_model_tables
        if table_name not in triggered_table_set
    )
    return status


def sync_pg_audit_triggers(using=DEFAULT_DB_ALIAS, config=None):
    db_connection = connections[using]
    audited_model_tables = get_audited_model_tables(config or get_pg_audit_config())

    if db_connection.vendor != "postgresql":
        return get_pg_audit_trigger_status(
            using=using,
            audited_model_tables=audited_model_tables,
        )

    with db_connection.cursor() as cursor:
        cursor.execute(build_create_triggers_sql(cursor, audited_model_tables))

    return get_pg_audit_trigger_status(
        using=using,
        audited_model_tables=audited_model_tables,
    )


def build_create_triggers_sql(cursor, audited_models):
    database_cursor = getattr(cursor, "cursor", cursor)
    audited_model_values = ", ".join(
        quote_sql_literal(database_cursor, table_name) for table_name in audited_models
    )
    audited_model_values = f"ARRAY[{audited_model_values}]::TEXT[]"
    return CREATE_TRIGGERS_SQL_TEMPLATE.format(
        audited_model_values=audited_model_values
    )


def quote_sql_literal(cursor, value):
    if hasattr(cursor, "mogrify"):
        return cursor.mogrify("%s", [value]).decode("utf-8")

    return "'%s'" % str(value).replace("'", "''")


@receiver(post_migrate)
def run_custom_post_migrate_hook(sender, *args, **kwargs):
    using = kwargs.get("using") or DEFAULT_DB_ALIAS
    if using in _configured_database_aliases:
        return

    db_connection = connections[using]
    if db_connection.vendor != "postgresql":
        return

    if not is_pg_audit_database_ready(using):
        return

    sync_pg_audit_triggers(using=using, config=get_pg_audit_config())
    _configured_database_aliases.add(using)
