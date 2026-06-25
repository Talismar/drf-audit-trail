from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS

from drf_audit_trail.pg_audit_models.signals import (
    get_pg_audit_trigger_status,
    sync_pg_audit_triggers,
)


class Command(BaseCommand):
    help = (
        "Synchronize PostgreSQL triggers used by drf_audit_trail.pg_audit_models "
        "with the current DRF_AUDIT_TRAIL_PG_AUDIT settings."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help="Database alias to synchronize. Defaults to 'default'.",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Only check whether triggers exist for the configured tables.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show configured audited tables and current trigger status.",
        )

    def handle(self, *args, **options):
        using = options["database"]

        if options["check"] or options["dry_run"]:
            status = get_pg_audit_trigger_status(using=using)
        else:
            status = sync_pg_audit_triggers(using=using)

        self.write_status(status)

        if status["database_vendor"] != "postgresql":
            raise CommandError(
                "pg_audit_models requires a PostgreSQL database. "
                f"Database '{using}' uses '{status['database_vendor']}'."
            )

        if options["check"] and status["missing_tables"]:
            missing_tables = ", ".join(status["missing_tables"])
            raise CommandError(
                f"Missing pg_audit_models triggers for: {missing_tables}"
            )

        if not options["check"] and not options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"pg_audit_models triggers synchronized on database '{using}'."
                )
            )

    def write_status(self, status):
        audited_tables = status["audited_tables"]
        triggered_tables = status["triggered_tables"]
        missing_tables = status["missing_tables"]

        self.stdout.write(f"Database alias: {status['database_alias']}")
        self.stdout.write(f"Database vendor: {status['database_vendor']}")
        self.stdout.write(f"Audited tables: {len(audited_tables)}")

        if audited_tables:
            self.stdout.write("Configured audited tables:")
            for table_name in audited_tables:
                self.stdout.write(f"  - {table_name}")
        else:
            self.stdout.write("Configured audited tables: none")

        if triggered_tables:
            self.stdout.write("Tables with pg_audit_models triggers:")
            for table_name in triggered_tables:
                self.stdout.write(f"  - {table_name}")
        else:
            self.stdout.write("Tables with pg_audit_models triggers: none")

        if missing_tables:
            self.stdout.write("Missing triggers:")
            for table_name in missing_tables:
                self.stdout.write(f"  - {table_name}")
        else:
            self.stdout.write("Missing triggers: none")
