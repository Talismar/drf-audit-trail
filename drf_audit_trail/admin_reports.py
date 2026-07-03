from django.http import HttpResponseBadRequest
from django.urls import path, reverse

from .report_export import AuditLogReportExporter, get_applied_filters_from_request


class AuditLogReportExportMixin:
    change_list_template = "admin/drf_audit_trail/auditlogentry/change_list.html"
    report_title = "Audit Log Report"
    report_filename = "audit_log_report"
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
    report_select_related = ()
    report_prefetch_related = ()

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

        changelist = self.get_changelist_instance(request)
        queryset = self.get_export_queryset(changelist)
        exporter = self.get_report_exporter()
        return exporter.export_response(request, queryset, export_format)

    def get_report_exporter(self):
        return AdminReportExporterAdapter(self)

    def get_export_queryset(self, changelist):
        queryset = changelist.queryset
        if self.report_select_related:
            queryset = queryset.select_related(*self.report_select_related)
        if self.report_prefetch_related:
            queryset = queryset.prefetch_related(*self.report_prefetch_related)
        return queryset

    def get_report_title(self):
        return self.report_title

    def get_report_filename(self):
        return self.report_filename

    def get_report_columns(self):
        return self.report_columns

    def get_report_rows(self, queryset):
        return [self.get_report_row(entry) for entry in queryset]

    def get_report_row(self, entry):
        raise NotImplementedError

    def get_report_user(self, request):
        return AdminReportExporterAdapter(self).get_report_user(request)

    def get_applied_filters(self, request):
        return get_applied_filters_from_request(request, ignored_params={"p", "all"})

    def format_report_value(self, value):
        return self.get_report_exporter().format_report_value(value)

    def format_audit_values(self, value):
        return self.get_report_exporter().format_audit_values(value)


class AdminReportExporterAdapter(AuditLogReportExporter):
    def __init__(self, admin_instance):
        self.admin = admin_instance
        super().__init__(
            report_title=admin_instance.report_title,
            report_filename=admin_instance.report_filename,
        )

    def get_report_title(self):
        return self.admin.get_report_title()

    def get_report_filename(self):
        return self.admin.get_report_filename()

    def get_report_columns(self):
        return self.admin.get_report_columns()

    def get_report_rows(self, queryset):
        return self.admin.get_report_rows(queryset)

    def get_report_user(self, request):
        return super().get_report_user(request)

    def get_applied_filters(self, request):
        return self.admin.get_applied_filters(request)
