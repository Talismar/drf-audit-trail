from .support import *


class AuditLogEntryAdminExportTestCase(TestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin",
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.request_audit_event = RequestAuditEvent.objects.create(
            method="PATCH",
            url="/api/products/1/",
            ip_addresses="192.168.1.10",
        )
        self.update_entry = AuditLogEntry.objects.create(
            request=self.request_audit_event,
            actor_identifier=str(self.user.pk),
            actor_role="Admin",
            actor_type=AuditLogEntry.USER,
            event_type="Update",
            action_description="Updated product price",
            content_type="core.product",
            object_id="1",
            object_repr="Product 1",
            field_name="price",
            old_values='{"price": "10.00"}',
            new_values='{"price": "12.00"}',
            reason_for_change="Correction after review",
        )
        self.view_entry = AuditLogEntry.objects.create(
            actor_identifier="system",
            actor_type=AuditLogEntry.SYSTEM,
            event_type="System Action",
            action_description="Auto-save product",
        )

    def test_changelist_should_show_export_links(self):
        response = self.client.get(
            reverse("admin:drf_audit_trail_auditlogentry_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Export CSV")
        self.assertContains(response, "Export XLS")
        self.assertContains(response, "Export PDF")

    def test_csv_export_should_include_header_filters_and_filtered_rows(self):
        response = self.client.get(
            reverse("admin:drf_audit_trail_auditlogentry_export", args=["csv"])
            + "?event_type__exact=Update"
        )

        content = response.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Who Pulled the report", content)
        self.assertIn("When the report was pulled", content)
        self.assertIn("event_type__exact=Update", content)
        self.assertIn("Updated product price", content)
        self.assertIn("price: 10.00", content)
        self.assertIn("price: 12.00", content)
        self.assertNotIn('{"price": "10.00"}', content)
        self.assertNotIn('{"price": "12.00"}', content)
        self.assertNotIn("Auto-save product", content)

    def test_xls_export_should_include_report_table(self):
        response = self.client.get(
            reverse("admin:drf_audit_trail_auditlogentry_export", args=["xls"])
            + "?event_type__exact=Update"
        )

        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.ms-excel; charset=utf-8",
        )
        self.assertIn("Who Pulled the report", content)
        self.assertIn("Updated product price", content)
        self.assertIn("price: 10.00", content)
        self.assertIn("price: 12.00", content)
        self.assertNotIn("&quot;price&quot;", content)
        self.assertNotIn("Auto-save product", content)

    @patch("drf_audit_trail.report_export.HTML")
    def test_pdf_export_should_render_report_pdf(self, html_mock):
        html_mock.return_value.write_pdf.return_value = b"%PDF-1.4"

        response = self.client.get(
            reverse("admin:drf_audit_trail_auditlogentry_export", args=["pdf"])
            + "?event_type__exact=Update"
        )
        html_string = html_mock.call_args.kwargs["string"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, b"%PDF-1.4")
        self.assertIn("Who Pulled the report", html_string)
        self.assertIn("Updated product price", html_string)
        self.assertIn("price: 10.00", html_string)
        self.assertIn("price: 12.00", html_string)
        self.assertNotIn("&quot;price&quot;", html_string)
        self.assertNotIn("Auto-save product", html_string)


class ProcessAuditEventAdminTestCase(TestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin",
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.process = ProcessAuditEvent.objects.create(
            name="Individual report process",
            created_by=str(self.user.pk),
        )
        self.other_process = ProcessAuditEvent.objects.create(
            name="Second report process",
            created_by=str(self.user.pk),
        )

    def test_changelist_should_show_download_button_for_each_process(self):
        response = self.client.get(
            reverse("admin:drf_audit_trail_processauditevent_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Download PDF", count=2)
        self.assertContains(
            response,
            reverse(
                "admin:drf_audit_trail_processauditevent_audit_report",
                args=[self.process.pk],
            ),
        )
        self.assertContains(
            response,
            reverse(
                "admin:drf_audit_trail_processauditevent_audit_report",
                args=[self.other_process.pk],
            ),
        )

    def test_change_view_should_show_audit_report_button_for_the_current_process(self):
        response = self.client.get(
            reverse(
                "admin:drf_audit_trail_processauditevent_change",
                args=[self.process.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Download Audit PDF")
        self.assertContains(
            response,
            reverse(
                "admin:drf_audit_trail_processauditevent_audit_report",
                args=[self.process.pk],
            ),
        )

    @patch("drf_audit_trail.admin.render_process_report_response")
    def test_admin_audit_report_should_download_pdf_for_specific_process(
        self, render_process_report_response_mock
    ):
        mocked_response = HttpResponse(
            b"%PDF-1.4",
            content_type="application/pdf",
        )
        mocked_response["Content-Disposition"] = (
            f'attachment; filename="process_audit_report_{self.process.pk}.pdf"'
        )
        render_process_report_response_mock.return_value = mocked_response

        response = self.client.get(
            reverse(
                "admin:drf_audit_trail_processauditevent_audit_report",
                args=[self.process.pk],
            )
        )

        render_process_report_response_mock.assert_called_once()
        report_processes = render_process_report_response_mock.call_args.args[0]
        self.assertEqual(len(report_processes), 1)
        self.assertEqual(report_processes[0].pk, self.process.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="process_audit_report_{self.process.pk}.pdf"',
        )
