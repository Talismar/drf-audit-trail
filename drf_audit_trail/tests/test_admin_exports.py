from .support import *


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
