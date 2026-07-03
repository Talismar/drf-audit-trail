from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ReadOnlyModelViewSet

from core.models import Category
from drf_audit_trail.api_report_export import AuditLogReportExportActionMixin
from drf_audit_trail.pg_audit_models.constants import SYSTEM, USER
from drf_audit_trail.pg_audit_models.models import ActionLog, DiffLog
from drf_audit_trail.pg_audit_models.reports import PGDiffLogReportExporter
from drf_audit_trail.tests.support import Client, TestCase, User


class TestDiffLogExportViewSet(
    AuditLogReportExportActionMixin,
    ReadOnlyModelViewSet,
):
    """Test-only consumer of the reusable export mixin."""

    permission_classes = [AllowAny]
    report_exporter_class = PGDiffLogReportExporter
    queryset = DiffLog.objects.select_related("action_log").order_by("-pk")

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if source := self.request.query_params.get("source"):
            queryset = queryset.filter(action_log__source__icontains=source)
        return queryset


router = SimpleRouter()
router.register("test-audit-logs", TestDiffLogExportViewSet, basename="audit-log")
urlpatterns = router.urls


@override_settings(ROOT_URLCONF=__name__)
class DiffLogAPIExportTests(TestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin",
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.action_log = ActionLog.objects.create(
            source="tests.update_category",
            ref_name=Category._meta.db_table,
            ref_id="1",
            username="admin",
            actor_type=USER,
            url="/api/categories/1/",
        )
        DiffLog.objects.create(
            action_log=self.action_log,
            event_type="UPDATE",
            ref_name=Category._meta.db_table,
            ref_id="1",
            column_name="name",
            old_value="Old category",
            new_value="New category",
            reason_for_change="Name correction",
        )
        DiffLog.objects.create(
            action_log=self.action_log,
            event_type="UPDATE",
            ref_name=Category._meta.db_table,
            ref_id="1",
            column_name="description",
            old_value="Old description",
            new_value="New description",
            reason_for_change="Description correction",
        )
        self.system_action_log = ActionLog.objects.create(
            source="tests.system_task",
            ref_name=Category._meta.db_table,
            ref_id="2",
            username="system",
            actor_type=SYSTEM,
            url="/tasks/categories/sync/",
        )
        DiffLog.objects.create(
            action_log=self.system_action_log,
            event_type="UPDATE",
            ref_name=Category._meta.db_table,
            ref_id="2",
            column_name="name",
            old_value="Draft",
            new_value="Synced",
            reason_for_change="System sync",
        )

    def test_csv_export_should_include_header_filters_and_filtered_rows(self):
        response = self.client.get(
            reverse("audit-log-export-report", args=["csv"])
            + "?source=tests.update_category"
        )

        content = response.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="pg_action_log_report.csv"',
        )
        self.assertIn("Who Pulled the report", content)
        self.assertIn("Filters applied", content)
        self.assertIn("source=tests.update_category", content)
        self.assertIn("Action Source", content)
        self.assertIn("tests.update_category", content)
        self.assertIn("Old category", content)
        self.assertIn("Description correction", content)
        self.assertNotIn("tests.system_task", content)

    def test_export_query_param_endpoint_should_support_format_csv(self):
        response = self.client.get(
            reverse("audit-log-export-report-query")
            + "?export_format=csv&source=tests.update_category"
        )

        content = response.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertIn("source=tests.update_category", content)
        self.assertIn("tests.update_category", content)
        self.assertNotIn("tests.system_task", content)

    def test_xls_export_should_include_report_table(self):
        response = self.client.get(
            reverse("audit-log-export-report", args=["xls"])
            + "?source=tests.update_category"
        )

        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.ms-excel; charset=utf-8",
        )
        self.assertIn("Who Pulled the report", content)
        self.assertIn("source=tests.update_category", content)
        self.assertIn("Old category", content)
        self.assertNotIn("tests.system_task", content)

    @patch("drf_audit_trail.report_export.HTML")
    def test_pdf_export_should_render_report_pdf(self, html_mock):
        html_mock.return_value.write_pdf.return_value = b"%PDF-1.4"

        response = self.client.get(
            reverse("audit-log-export-report", args=["pdf"])
            + "?source=tests.update_category"
        )
        html_string = html_mock.call_args.kwargs["string"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, b"%PDF-1.4")
        self.assertIn("Who Pulled the report", html_string)
        self.assertIn("source=tests.update_category", html_string)
        self.assertIn("Old category", html_string)
        self.assertNotIn("tests.system_task", html_string)
