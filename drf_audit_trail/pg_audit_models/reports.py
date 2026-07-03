from django.db.models import Prefetch

from drf_audit_trail.report_export import AuditLogReportExporter

from .models import DiffLog


class PGAuditLogReportFieldMixin:
    report_field_resolvers = (
        ("Timestamp (UTC)", "executed_at"),
        ("Username", "username"),
        ("User Role", "actor_role"),
        ("Event Type", "event_type"),
        ("Action Source", "source"),
        ("Object", "object_reference"),
        ("Field Name", "field_name"),
        ("Old Value", "old_value"),
        ("New Value", "new_value"),
        ("Reason for Change", "reason_for_change"),
        ("System/User Action", "actor_type"),
        ("URL", "url"),
    )

    def get_report_columns(self):
        return tuple(label for label, _ in self.report_field_resolvers)

    def get_report_row(self, action_log, diff_log):
        return tuple(
            self.resolve_report_field(action_log, diff_log, field_name)
            for _, field_name in self.report_field_resolvers
        )

    def resolve_report_field(self, action_log, diff_log, field_name):
        resolver = getattr(self, f"resolve_report_{field_name}")
        return resolver(action_log, diff_log)

    def resolve_report_executed_at(self, action_log, diff_log):
        return self.format_report_value(action_log.executed_at)

    def resolve_report_username(self, action_log, diff_log):
        return self.format_report_value(action_log.username)

    def resolve_report_actor_role(self, action_log, diff_log):
        return action_log.actor_role if action_log.actor_role else ""

    def resolve_report_event_type(self, action_log, diff_log):
        return self.format_report_value(diff_log.event_type if diff_log else None)

    def resolve_report_source(self, action_log, diff_log):
        return self.format_report_value(action_log.source)

    def resolve_report_object_reference(self, action_log, diff_log):
        if diff_log:
            model_name = diff_log.model_verbose_name
            ref_id = diff_log.ref_id
        else:
            model_name = action_log.model_verbose_name
            ref_id = action_log.ref_id

        if model_name and ref_id:
            return self.format_report_value(f"{model_name}:{ref_id}")
        return ""

    def resolve_report_field_name(self, action_log, diff_log):
        return self.format_report_value(
            diff_log.field_verbose_name if diff_log else None
        )

    def resolve_report_old_value(self, action_log, diff_log):
        return self.format_audit_values(diff_log.get_old_value() if diff_log else None)

    def resolve_report_new_value(self, action_log, diff_log):
        return self.format_audit_values(diff_log.get_new_value() if diff_log else None)

    def resolve_report_reason_for_change(self, action_log, diff_log):
        return self.format_report_value(
            diff_log.reason_for_change if diff_log else None
        )

    def resolve_report_actor_type(self, action_log, diff_log):
        return self.format_report_value(action_log.actor_type)

    def resolve_report_url(self, action_log, diff_log):
        return self.format_report_value(action_log.url)


class PGAuditLogReportExporter(PGAuditLogReportFieldMixin, AuditLogReportExporter):
    report_title = "PostgreSQL Audit Log Report"
    report_filename = "pg_action_log_report"

    def get_report_rows(self, queryset):
        rows = []
        for action_log in queryset:
            diff_logs = list(action_log.difflog_set.all())
            if not diff_logs:
                rows.append(self.get_report_row(action_log, None))
                continue
            rows.extend(
                self.get_report_row(action_log, diff_log) for diff_log in diff_logs
            )
        return rows

    def prepare_action_log_queryset(self, queryset):
        return queryset.prefetch_related(
            Prefetch("difflog_set", queryset=DiffLog.objects.order_by("id"))
        )


class PGDiffLogReportExporter(PGAuditLogReportFieldMixin, AuditLogReportExporter):
    report_title = "PostgreSQL Audit Log Report"
    report_filename = "pg_action_log_report"

    def get_report_rows(self, queryset):
        return [
            self.get_report_row(diff_log.action_log, diff_log)
            for diff_log in queryset.select_related("action_log")
        ]

    def prepare_diff_log_queryset(self, queryset):
        return queryset.select_related("action_log")
