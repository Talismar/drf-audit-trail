import csv

from django.http import HttpResponse, HttpResponseBadRequest
from django.template.loader import get_template
from django.utils import timezone
from weasyprint import HTML

from .utils import deserialize_audit_value

DEFAULT_IGNORED_FILTER_PARAMS = frozenset(
    {
        "p",
        "all",
        "page",
        "page_size",
        "limit",
        "offset",
        "ordering",
        "format",
        "export_format",
    }
)


def get_applied_filters_from_request(request, ignored_params=None):
    ignored_params = ignored_params or DEFAULT_IGNORED_FILTER_PARAMS
    query_params = getattr(request, "query_params", None) or request.GET
    filters = []

    for key, values in query_params.lists():
        if key in ignored_params:
            continue
        filters.append(
            {
                "name": key,
                "value": ", ".join(str(value) for value in values),
            }
        )
    return filters


class AuditLogReportExporter:
    report_title = "Audit Log Report"
    report_filename = "audit_log_report"
    ignored_filter_params = DEFAULT_IGNORED_FILTER_PARAMS

    def __init__(
        self,
        *,
        report_title=None,
        report_filename=None,
        ignored_filter_params=None,
    ):
        if report_title is not None:
            self.report_title = report_title
        if report_filename is not None:
            self.report_filename = report_filename
        if ignored_filter_params is not None:
            self.ignored_filter_params = ignored_filter_params

    def get_report_title(self):
        return self.report_title

    def get_report_filename(self):
        return self.report_filename

    def get_report_columns(self):
        raise NotImplementedError

    def get_report_rows(self, queryset):
        raise NotImplementedError

    def get_report_user(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return str(user)
        return "Anonymous"

    def get_applied_filters(self, request):
        return get_applied_filters_from_request(
            request,
            ignored_params=self.ignored_filter_params,
        )

    def build_export_context(self, request, queryset):
        return {
            "title": self.get_report_title(),
            "pulled_by": self.get_report_user(request),
            "pulled_at": timezone.now(),
            "filters": self.get_applied_filters(request),
            "columns": self.get_report_columns(),
            "rows": self.get_report_rows(queryset),
        }

    def export_response(self, request, queryset, export_format):
        export_format = (export_format or "").lower()
        if export_format not in {"csv", "xls", "pdf"}:
            return HttpResponseBadRequest("Unsupported export format.")

        context = self.build_export_context(request, queryset)
        if export_format == "csv":
            return self.render_csv_export(context)
        if export_format == "xls":
            return self.render_xls_export(context)
        return self.render_pdf_export(context)

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

    def format_filters_for_export(self, context):
        filters = context["filters"]
        if not filters:
            return ""
        return "; ".join(f"{item['name']}={item['value']}" for item in filters)

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
