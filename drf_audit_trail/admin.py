from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse

from .admin_reports import AuditLogReportExportMixin
from .models import (
    AuditLogEntry,
    LoginAuditEvent,
    ProcessAuditEvent,
    RegistrationAuditEvent,
    RequestAuditEvent,
    StepAuditEvent,
)
from .utils import get_user_by_pk_name
from .views import get_process_for_report, render_process_report_response


class ReadonlyAdminMixin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RequestAuditEventModelAdmin(ReadonlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "method",
        "url",
        "status_code",
        "_user",
        "datetime",
        "request_type",
    )
    list_filter = ("method", "ip_addresses")
    search_fields = ("method", "ip_addresses", "status_code", "user", "url")

    def _user(self, obj: RequestAuditEvent):
        return get_user_by_pk_name(obj.user)


admin.site.register(RequestAuditEvent, RequestAuditEventModelAdmin)


class AuditLogEntryModelAdmin(
    AuditLogReportExportMixin, ReadonlyAdminMixin, admin.ModelAdmin
):
    list_display = (
        "id",
        "event_type",
        "_actor_identifier",
        "actor_type",
        "field_name",
        "content_type",
        "object_id",
        "request",
        "datetime",
    )
    list_filter = ("event_type", "actor_type", "content_type")
    search_fields = (
        "event_type",
        "action_description",
        "actor_role",
        "content_type",
        "object_id",
        "object_repr",
        "field_name",
        "reason_for_change",
    )
    report_select_related = ("request",)

    def _actor_identifier(self, obj: AuditLogEntry):
        return get_user_by_pk_name(obj.actor_identifier)

    def get_report_row(self, entry: AuditLogEntry):
        return (
            self.format_report_value(entry.datetime),
            self.format_report_value(get_user_by_pk_name(entry.actor_identifier)),
            self.format_report_value(entry.actor_role),
            self.format_report_value(entry.event_type),
            self.format_report_value(entry.action_description),
            self.format_report_value(
                entry.object_repr or self.get_object_reference(entry)
            ),
            self.format_report_value(entry.field_name),
            self.format_audit_values(entry.old_values),
            self.format_audit_values(entry.new_values),
            self.format_report_value(entry.reason_for_change),
            self.format_report_value(entry.actor_type),
            self.format_report_value(
                entry.request.ip_addresses if entry.request is not None else None
            ),
        )

    def get_object_reference(self, entry: AuditLogEntry):
        if entry.content_type and entry.object_id:
            return f"{entry.content_type}:{entry.object_id}"
        return None


admin.site.register(AuditLogEntry, AuditLogEntryModelAdmin)


class LoginAuditEventModelAdmin(ReadonlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "datetime",
        "request_ip_addresses",
        "request__status_code",
    )
    list_filter = ("status",)
    search_fields = ("request__ip_addresses", "request__user", "request__url")
    readonly_fields = ["request"]

    @admin.display()
    def request_ip_addresses(self, obj):
        if obj.request is not None:
            return obj.request.ip_addresses

    @admin.display()
    def request__status_code(self, obj):
        if obj.request is not None:
            return obj.request.status_code

    def user(self, obj):
        if obj.request is not None:
            return get_user_by_pk_name(obj.request.user)


admin.site.register(LoginAuditEvent, LoginAuditEventModelAdmin)


class ProcessAuditEventModelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "success", "request", "user", "download_audit_pdf")
    list_filter = ("name",)
    search_fields = ("name",)
    change_form_template = "admin/drf_audit_trail/processauditevent/change_form.html"

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        custom_urls = [
            path(
                "<path:object_id>/audit-report/",
                self.admin_site.admin_view(self.audit_report_view),
                name=f"{opts.app_label}_{opts.model_name}_audit_report",
            )
        ]
        return custom_urls + urls

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["audit_report_url"] = self.get_audit_report_url(object_id)
        return super().change_view(
            request,
            object_id,
            form_url=form_url,
            extra_context=extra_context,
        )

    def audit_report_view(self, request, object_id):
        process = get_process_for_report(object_id)
        return render_process_report_response(
            [process],
            filename=f"process_audit_report_{process.pk}.pdf",
            content_disposition="attachment",
        )

    def get_audit_report_url(self, object_id):
        opts = self.model._meta
        return reverse(
            f"admin:{opts.app_label}_{opts.model_name}_audit_report",
            args=[object_id],
            current_app=self.admin_site.name,
        )

    @admin.display(description="Audit PDF")
    def download_audit_pdf(self, obj):
        return format_html(
            '<a class="button" href="{}">Download PDF</a>',
            self.get_audit_report_url(obj.pk),
        )

    def user(self, obj):
        return get_user_by_pk_name(obj.created_by)

    @admin.display(boolean=True)
    def success(self, obj):
        if obj.steps.filter(registrations__success=False).exists():
            return False
        return True


admin.site.register(ProcessAuditEvent, ProcessAuditEventModelAdmin)


class StepAuditEventModelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "success", "process", "user")
    list_filter = ("name",)
    search_fields = ("name",)

    def user(self, obj):
        return get_user_by_pk_name(obj.created_by)

    @admin.display(boolean=True)
    def success(self, obj):
        if obj.registrations.filter(success=True).count() == obj.total_registrations:
            return True
        return False


admin.site.register(StepAuditEvent, StepAuditEventModelAdmin)


class RegistrationAuditEventModelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "success", "step", "user")
    list_filter = ("success",)
    search_fields = ("message",)

    # @admin.display()
    # def step_name(self, obj):
    #     if obj.step is not None:
    #         return obj.step.name

    def user(self, obj):
        return get_user_by_pk_name(obj.created_by)


admin.site.register(RegistrationAuditEvent, RegistrationAuditEventModelAdmin)
