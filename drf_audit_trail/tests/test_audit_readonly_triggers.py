import uuid
from unittest import SkipTest

from django.db import DatabaseError, connections, transaction
from django.test import TransactionTestCase

from drf_audit_trail.models import RequestAuditEvent
from drf_audit_trail.pg_audit_models.models import ActionLog, DiffLog
from drf_audit_trail.settings import DJANGO_DEFAULT_DATABASE_ALIAS


EXPECTED_READONLY_TRIGGERS = {
    "drf_audit_trail_loginauditevent": {
        "trg_loginauditevent_no_delete",
        "trg_loginauditevent_no_update",
    },
    "drf_audit_trail_requestauditevent": {
        "trg_requestauditevent_no_delete",
        "trg_requestauditevent_no_update",
    },
    "pg_audit_models_actionlog": {
        "trg_actionlog_no_delete",
        "trg_actionlog_no_update",
    },
    "pg_audit_models_difflog": {
        "trg_difflog_no_delete",
        "trg_difflog_no_update",
    },
}


class AuditReadonlyTriggersTestCase(TransactionTestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.table_database_aliases = self.get_table_database_aliases()
        self.request_audit_database_alias = self.get_database_alias_for_table(
            RequestAuditEvent._meta.db_table
        )
        self.pg_audit_database_alias = self.get_database_alias_for_table(
            ActionLog._meta.db_table
        )

    def test_readonly_triggers_should_exist_for_audit_tables(self):
        found_triggers = self.get_readonly_triggers_by_table()

        self.assertEqual(found_triggers, EXPECTED_READONLY_TRIGGERS)

    def test_drf_audit_trail_signal_should_not_configure_pg_audit_models(self):
        from drf_audit_trail.signals import get_audit_model_table_names

        table_names = {table_name for _, table_name in get_audit_model_table_names()}

        self.assertNotIn(ActionLog._meta.db_table, table_names)
        self.assertNotIn(DiffLog._meta.db_table, table_names)

    def test_pg_audit_models_signal_should_configure_pg_audit_models(self):
        from drf_audit_trail.pg_audit_models.signals import (
            get_pg_audit_readonly_model_table_names,
        )

        table_names = {
            table_name
            for _, table_name in get_pg_audit_readonly_model_table_names()
        }

        self.assertEqual(
            table_names,
            {
                ActionLog._meta.db_table,
                DiffLog._meta.db_table,
            },
        )

    def test_pg_audit_models_readonly_triggers_should_use_primary_database(self):
        self.assertEqual(
            self.pg_audit_database_alias,
            DJANGO_DEFAULT_DATABASE_ALIAS,
        )

    def test_update_on_audit_table_should_raise_readonly_trigger_error(self):
        with self.assertRaisesMessage(
            DatabaseError,
            (
                'Audit table "drf_audit_trail_requestauditevent" is read-only. '
                "Operation UPDATE is not allowed."
            ),
        ):
            with transaction.atomic(using=self.request_audit_database_alias):
                event = self.create_request_audit_event("update")

                RequestAuditEvent.objects.using(
                    self.request_audit_database_alias
                ).filter(pk=event.pk).update(method="POST")

        self.assert_request_audit_event_was_rolled_back(event)

    def test_delete_on_audit_table_should_raise_readonly_trigger_error(self):
        with self.assertRaisesMessage(
            DatabaseError,
            (
                'Audit table "drf_audit_trail_requestauditevent" is read-only. '
                "Operation DELETE is not allowed."
            ),
        ):
            with transaction.atomic(using=self.request_audit_database_alias):
                event = self.create_request_audit_event("delete")

                RequestAuditEvent.objects.using(
                    self.request_audit_database_alias
                ).filter(pk=event.pk).delete()

        self.assert_request_audit_event_was_rolled_back(event)

    def test_update_on_action_log_should_raise_readonly_trigger_error(self):
        with self.assertRaisesMessage(
            DatabaseError,
            (
                'Audit table "pg_audit_models_actionlog" is read-only. '
                "Operation UPDATE is not allowed."
            ),
        ):
            with transaction.atomic(using=self.pg_audit_database_alias):
                action_log = self.create_action_log("update")

                ActionLog.objects.using(self.pg_audit_database_alias).filter(
                    pk=action_log.pk
                ).update(source="changed")

        self.assert_action_log_was_rolled_back(action_log)

    def test_delete_on_action_log_should_raise_readonly_trigger_error(self):
        with self.assertRaisesMessage(
            DatabaseError,
            (
                'Audit table "pg_audit_models_actionlog" is read-only. '
                "Operation DELETE is not allowed."
            ),
        ):
            with transaction.atomic(using=self.pg_audit_database_alias):
                action_log = self.create_action_log("delete")

                ActionLog.objects.using(self.pg_audit_database_alias).filter(
                    pk=action_log.pk
                ).delete()

        self.assert_action_log_was_rolled_back(action_log)

    def test_update_on_diff_log_should_raise_readonly_trigger_error(self):
        with self.assertRaisesMessage(
            DatabaseError,
            (
                'Audit table "pg_audit_models_difflog" is read-only. '
                "Operation UPDATE is not allowed."
            ),
        ):
            with transaction.atomic(using=self.pg_audit_database_alias):
                diff_log = self.create_diff_log("update")

                DiffLog.objects.using(self.pg_audit_database_alias).filter(
                    pk=diff_log.pk
                ).update(new_value="changed")

        self.assert_diff_log_was_rolled_back(diff_log)

    def test_delete_on_diff_log_should_raise_readonly_trigger_error(self):
        with self.assertRaisesMessage(
            DatabaseError,
            (
                'Audit table "pg_audit_models_difflog" is read-only. '
                "Operation DELETE is not allowed."
            ),
        ):
            with transaction.atomic(using=self.pg_audit_database_alias):
                diff_log = self.create_diff_log("delete")

                DiffLog.objects.using(self.pg_audit_database_alias).filter(
                    pk=diff_log.pk
                ).delete()

        self.assert_diff_log_was_rolled_back(diff_log)

    def get_table_database_aliases(self):
        table_database_aliases = {}
        for database_alias in connections:
            connection = connections[database_alias]
            if connection.vendor != "postgresql":
                continue

            table_names = set(connection.introspection.table_names())
            for table_name in EXPECTED_READONLY_TRIGGERS:
                if table_name in table_names:
                    table_database_aliases[table_name] = database_alias

        if not table_database_aliases:
            raise SkipTest("PostgreSQL audit tables are not available.")

        return table_database_aliases

    def get_database_alias_for_table(self, table_name):
        try:
            return self.table_database_aliases[table_name]
        except KeyError:
            raise SkipTest(f"PostgreSQL audit table is not available: {table_name}.")

    def get_readonly_triggers_by_table(self):
        found_triggers = {
            table_name: set() for table_name in EXPECTED_READONLY_TRIGGERS
        }

        for (
            database_alias,
            table_names,
        ) in self.group_tables_by_database_alias().items():
            connection = connections[database_alias]
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.relname, t.tgname
                    FROM pg_trigger t
                    JOIN pg_class c ON c.oid = t.tgrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE NOT t.tgisinternal
                      AND n.nspname = 'public'
                      AND c.relname = ANY(%s)
                      AND t.tgname LIKE %s
                    ORDER BY c.relname, t.tgname
                    """,
                    [table_names, "%_no_%"],
                )

                for table_name, trigger_name in cursor.fetchall():
                    found_triggers[table_name].add(trigger_name)

        return found_triggers

    def group_tables_by_database_alias(self):
        tables_by_database_alias = {}
        for table_name, database_alias in self.table_database_aliases.items():
            tables_by_database_alias.setdefault(database_alias, []).append(table_name)
        return tables_by_database_alias

    def create_request_audit_event(self, operation):
        test_id = uuid.uuid4()
        return RequestAuditEvent.objects.using(
            self.request_audit_database_alias
        ).create(
            method="GET",
            url=f"/audit-readonly-trigger-test/{operation}/{test_id}/",
            ip_addresses="127.0.0.1",
        )

    def create_action_log(self, operation):
        test_id = uuid.uuid4()
        return ActionLog.objects.using(self.pg_audit_database_alias).create(
            source=f"audit-readonly-trigger-test-{operation}-{test_id}",
            ref_name="test_table",
            ref_id=str(test_id),
            username="trigger-test",
        )

    def create_diff_log(self, operation):
        action_log = self.create_action_log(f"diff-{operation}")
        return DiffLog.objects.using(self.pg_audit_database_alias).create(
            action_log=action_log,
            event_type="UPDATE",
            ref_name="test_table",
            ref_id=str(uuid.uuid4()),
            column_name="name",
            old_value="old",
            new_value="new",
        )

    def assert_request_audit_event_was_rolled_back(self, event):
        exists = (
            RequestAuditEvent.objects.using(self.request_audit_database_alias)
            .filter(url=event.url)
            .exists()
        )
        self.assertFalse(exists)

    def assert_action_log_was_rolled_back(self, action_log):
        exists = (
            ActionLog.objects.using(self.pg_audit_database_alias)
            .filter(pk=action_log.pk)
            .exists()
        )
        self.assertFalse(exists)

    def assert_diff_log_was_rolled_back(self, diff_log):
        exists = (
            DiffLog.objects.using(self.pg_audit_database_alias)
            .filter(pk=diff_log.pk)
            .exists()
        )
        self.assertFalse(exists)
