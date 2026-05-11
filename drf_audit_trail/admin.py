import csv


from django.contrib import admin
from django.http import HttpResponse, HttpResponseBadRequest
from django.template.loader import get_template
from django.utils import timezone
from django.utils.html import format_html
from django.urls import path, reverse
from weasyprint import HTML

from .models import (
    AuditLogEntry,
    LoginAuditEvent,
    ProcessAuditEvent,
    RegistrationAuditEvent,
    RequestAuditEvent,
    StepAuditEvent,
)
from .utils import deserialize_audit_value, get_user_by_pk_name
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


class AuditLogEntryModelAdmin(ReadonlyAdminMixin, admin.ModelAdmin):
    change_list_template = "admin/drf_audit_trail/auditlogentry/change_list.html"
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

    report_columns = (
        "Timestamp (UTC)",
        "User ID",
        "User Role",
        "Event Type",
        "Action Description",
        "Object (Subject/Visit)",
        "Field Name",
        "Old Value",
        "New Value",
        "Reason for Change",
        "System/User Action",
        "Device/IP",
    )

    def _actor_identifier(self, obj: AuditLogEntry):
        return get_user_by_pk_name(obj.actor_identifier)

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        custom_urls = [
            path(
                "export/<str:export_format>/",
                self.admin_site.admin_view(self.export_view),
                name=f"{opts.app_label}_{opts.model_name}_export",
            )
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["audit_log_export_csv_url"] = self.get_export_url(request, "csv")
        extra_context["audit_log_export_xls_url"] = self.get_export_url(request, "xls")
        extra_context["audit_log_export_pdf_url"] = self.get_export_url(request, "pdf")
        return super().changelist_view(request, extra_context=extra_context)

    def get_export_url(self, request, export_format):
        opts = self.model._meta
        url = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_export",
            args=[export_format],
            current_app=self.admin_site.name,
        )
        query_string = request.GET.urlencode()
        if query_string:
            return f"{url}?{query_string}"
        return url

    def export_view(self, request, export_format):
        export_format = export_format.lower()
        if export_format not in {"csv", "xls", "pdf"}:
            return HttpResponseBadRequest("Unsupported export format.")

        context = self.get_export_context(request)
        if export_format == "csv":
            return self.render_csv_export(context)
        if export_format == "xls":
            return self.render_xls_export(context)
        return self.render_pdf_export(context)

    def get_export_context(self, request):
        changelist = self.get_changelist_instance(request)
        queryset = changelist.queryset.select_related("request")
        return {
            "title": "Audit Log Report",
            "pulled_by": self.get_report_user(request),
            "pulled_at": timezone.now(),
            "filters": self.get_applied_filters(request),
            "columns": self.report_columns,
            "rows": [self.get_report_row(entry) for entry in queryset],
        }

    def get_report_user(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return str(user)
        return "Anonymous"

    def get_applied_filters(self, request):
        ignored_params = {"p", "all"}
        filters = []
        for key, values in request.GET.lists():
            if key in ignored_params:
                continue
            filters.append(
                {
                    "name": key,
                    "value": ", ".join(values),
                }
            )
        return filters

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

    def format_report_value(self, value):
        value = deserialize_audit_value(value)
        if value in (None, ""):
            return ""
        if isinstance(value, (dict, list, tuple)):
            return self.format_structured_report_value(value)
        return str(value)

    def format_audit_values(self, value):
        value = deserialize_audit_value(value)
        if value in (None, ""):
            return ""

        formatted_value = self.format_structured_report_value(value)
        return formatted_value or ""

    def format_structured_report_value(self, value, prefix=""):
        if isinstance(value, dict):
            parts = []
            for key, child_value in value.items():
                child_prefix = f"{prefix}.{key}" if prefix else str(key)
                parts.append(
                    self.format_structured_report_value(child_value, child_prefix)
                )
            return "; ".join(part for part in parts if part)

        if isinstance(value, (list, tuple)):
            if not value:
                return f"{prefix}: null" if prefix else "null"

            if all(not isinstance(item, (dict, list, tuple)) for item in value):
                values = ", ".join(
                    self.format_scalar_report_value(item) for item in value
                )
                return f"{prefix}: {values}" if prefix else values

            parts = []
            for index, child_value in enumerate(value, start=1):
                child_prefix = f"{prefix}[{index}]" if prefix else f"Item {index}"
                parts.append(
                    self.format_structured_report_value(child_value, child_prefix)
                )
            return "; ".join(part for part in parts if part)

        formatted_value = self.format_scalar_report_value(value)
        return f"{prefix}: {formatted_value}" if prefix else formatted_value

    def format_scalar_report_value(self, value):
        if value in (None, ""):
            return ""
        return str(value)

    def render_csv_export(self, context):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="audit_log_report.csv"'
        response.write("\ufeff")

        writer = csv.writer(response)
        writer.writerow(["Who Pulled the report", context["pulled_by"]])
        writer.writerow(["When the report was pulled", context["pulled_at"]])
        writer.writerow(["Filters applied", self.format_filters_for_export(context)])
        writer.writerow([])
        writer.writerow(context["columns"])
        writer.writerows(context["rows"])
        return response

    def render_xls_export(self, context):
        template = get_template("admin/drf_audit_trail/auditlogentry/report_xls.html")
        response = HttpResponse(
            template.render(context),
            content_type="application/vnd.ms-excel; charset=utf-8",
        )
        response["Content-Disposition"] = 'attachment; filename="audit_log_report.xls"'
        return response

    def render_pdf_export(self, context):
        template = get_template("admin/drf_audit_trail/auditlogentry/report_pdf.html")
        html_content = template.render(context)
        pdf_file = HTML(string=html_content).write_pdf()

        response = HttpResponse(pdf_file, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="audit_log_report.pdf"'
        return response

    def format_filters_for_export(self, context):
        filters = context["filters"]
        if not filters:
            return ""
        return "; ".join(f"{item['name']}={item['value']}" for item in filters)


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
