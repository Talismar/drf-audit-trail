from django.contrib import admin

from drf_audit_trail.admin import ReadonlyAdminMixin
from drf_audit_trail.admin_reports import AuditLogReportExportMixin

from .models import ActionLog, DiffLog
from .reports import PGAuditLogReportExporter


class DiffLogInline(admin.TabularInline):
    model = DiffLog
    max_num = 0


@admin.register(ActionLog)
class ActionLogAdmin(AuditLogReportExportMixin, ReadonlyAdminMixin):
    report_title = "PostgreSQL Audit Log Report"
    report_filename = "pg_action_log_report"
    list_display = (
        "id",
        "source",
        "get_ref_name",
        "ref_id",
        "ref",
        "executed_at",
        "username",
        "actor_type",
        "url",
        "extra_informations",
    )
    list_filter = ("source", "username", "actor_type", "executed_at")
    search_fields = (
        "source",
        "username",
        "url",
        "ref_name",
        "ref_id",
        "difflog__event_type",
        "difflog__column_name",
        "difflog__old_value",
        "difflog__new_value",
        "difflog__reason_for_change",
    )
    inlines = (DiffLogInline,)

    def ref(self, obj):
        return obj.get_ref() if obj else None

    def get_ref_name(self, obj):
        return obj.model_verbose_name if obj else None

    get_ref_name.short_description = "model"

    def get_report_exporter(self):
        return PGAuditLogReportExporter()

    def get_export_queryset(self, changelist):
        return self.get_report_exporter().prepare_action_log_queryset(
            changelist.queryset
        )

    def get_report_columns(self):
        return self.get_report_exporter().get_report_columns()

    def get_report_rows(self, queryset):
        return self.get_report_exporter().get_report_rows(queryset)
