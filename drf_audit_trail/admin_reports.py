import csv

from django.http import HttpResponse, HttpResponseBadRequest
from django.template.loader import get_template
from django.urls import path, reverse
from django.utils import timezone
from weasyprint import HTML

from .utils import deserialize_audit_value


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

        context = self.get_export_context(request)
        if export_format == "csv":
            return self.render_csv_export(context)
        if export_format == "xls":
            return self.render_xls_export(context)
        return self.render_pdf_export(context)

    def get_export_context(self, request):
        changelist = self.get_changelist_instance(request)
        queryset = self.get_export_queryset(changelist)
        return {
            "title": self.get_report_title(),
            "pulled_by": self.get_report_user(request),
            "pulled_at": timezone.now(),
            "filters": self.get_applied_filters(request),
            "columns": self.get_report_columns(),
            "rows": self.get_report_rows(queryset),
        }

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
        filename = self.get_report_filename()
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
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
        response["Content-Disposition"] = (
            f'attachment; filename="{self.get_report_filename()}.xls"'
        )
        return response

    def render_pdf_export(self, context):
        template = get_template("admin/drf_audit_trail/auditlogentry/report_pdf.html")
        html_content = template.render(context)
        pdf_file = HTML(string=html_content).write_pdf()

        response = HttpResponse(pdf_file, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{self.get_report_filename()}.pdf"'
        )
        return response

    def format_filters_for_export(self, context):
        filters = context["filters"]
        if not filters:
            return ""
        return "; ".join(f"{item['name']}={item['value']}" for item in filters)
