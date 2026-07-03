from rest_framework.decorators import action

from .report_export import AuditLogReportExporter


class AuditLogReportExportActionMixin:
    """Add audit-log report export actions to a DRF viewset.

    Subclasses should set ``report_exporter_class`` and optionally override
    ``get_report_exporter`` / ``get_export_queryset``. The export action uses
    the viewset's ``filter_queryset`` pipeline, so django-filter (or any custom
    filtering) applied to list endpoints is reused automatically.

    Query parameters from ``request.query_params`` are collected and rendered
    in the report header under "Filters applied", except for pagination and
    export control params (``page``, ``format``, etc.).

    Example::

        class DiffLogViewSet(AuditLogReportExportActionMixin, ReadOnlyModelViewSet):
            report_exporter_class = PGDiffLogReportExporter
            queryset = DiffLog.objects.select_related("action_log")
            filterset_class = DiffLogFilterSet

            @action(detail=False, methods=["get"])
            def diff_logs(self, request):
                ...
    """

    report_exporter_class = AuditLogReportExporter

    def get_report_exporter(self):
        return self.report_exporter_class()

    def get_export_queryset(self):
        return self.filter_queryset(self.get_queryset())

    @action(
        detail=False,
        methods=["get"],
        url_path=r"export/(?P<export_format>csv|xls|pdf)",
    )
    def export_report(self, request, export_format=None):
        exporter = self.get_report_exporter()
        queryset = self.get_export_queryset()
        queryset = self.prepare_report_queryset(queryset, exporter)
        return exporter.export_response(request, queryset, export_format)

    @action(detail=False, methods=["get"], url_path="export")
    def export_report_query(self, request):
        export_format = request.query_params.get("export_format", "csv")
        exporter = self.get_report_exporter()
        queryset = self.get_export_queryset()
        queryset = self.prepare_report_queryset(queryset, exporter)
        return exporter.export_response(request, queryset, export_format)

    def prepare_report_queryset(self, queryset, exporter):
        prepare_action_log = getattr(exporter, "prepare_action_log_queryset", None)
        if prepare_action_log is not None and self._uses_action_log_queryset():
            return prepare_action_log(queryset)

        prepare_diff_log = getattr(exporter, "prepare_diff_log_queryset", None)
        if prepare_diff_log is not None:
            return prepare_diff_log(queryset)

        return queryset

    def _uses_action_log_queryset(self):
        model = self.get_queryset().model
        return model._meta.label.endswith(".ActionLog")
