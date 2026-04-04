import io
import logging
from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import Client, TestCase
from django.urls import reverse

from drf_audit_trail.models import LoginAuditEvent, ProcessAuditEvent, RequestAuditEvent


class MiddlewareTestCase(TestCase):
    databases = {"default", "audit_trail"}

    def _get_client_with_login(self):
        user_data = {"username": "talismar", "password": "admin"}
        User.objects.create_user(**user_data)

        client = Client()
        response = client.post("/api/token/", data=user_data)
        token = response.json()["access"]

        return Client(HTTP_Authorization="Bearer " + token)

    def test_should_store_a_login_audit_event_for_auth_request(self):
        User.objects.create_user(username="talismar", password="admin")

        client = Client()

        request_data = {"username": "talismar", "password": "admin"}
        client.post("/api/token/", data=request_data)

        login_audit_event = LoginAuditEvent.objects.all()

        self.assertEqual(login_audit_event.count(), 1)
        self.assertEqual(login_audit_event[0].status, LoginAuditEvent.SIGNIN)

    def test_should_store_a_login_audit_event_for_auth_request_with_falied_status(
        self,
    ):
        client = Client()

        request_data = {"username": "talismar", "password": "admin"}
        client.post("/api/token/", data=request_data)

        login_audit_event = LoginAuditEvent.objects.all()

        self.assertEqual(login_audit_event.count(), 1)
        self.assertEqual(login_audit_event[0].status, LoginAuditEvent.FAILED)

    def test_should_store_a_request_audit_event_for_any_request_not_found_that_request_url_match(
        self,
    ):
        client = Client()

        client.get("/api/fake-endpoint/")

        request_audit_event = RequestAuditEvent.objects.all()

        self.assertEqual(request_audit_event.count(), 1)
        self.assertEqual(request_audit_event[0].method, "GET")
        self.assertEqual(request_audit_event[0].status_code, 404)
        self.assertEqual(request_audit_event[0].query_params, "")
        self.assertIsNone(request_audit_event[0].user)

    def test_should_store_the_request_user_for_protected_endpoint_or_when_user_is_authenticated(
        self,
    ):
        client = self._get_client_with_login()

        response = client.get("/api/protected-endpoint/")

        request_audit_event = RequestAuditEvent.objects.filter(
            url="/api/protected-endpoint/"
        ).first()

        self.assertIsNotNone(request_audit_event.user)
        self.assertEqual(request_audit_event.user, "1")
        self.assertEqual(response.status_code, request_audit_event.status_code)

    def test_url_and_query_params_are_truncated(self):
        long_url = "/api/test/" + ("a" * 3000)
        long_query = "param=" + ("b" * 3000)
        client = Client()
        # Simula request com url e query_params longos
        client.get(long_url + "?" + long_query)
        event = RequestAuditEvent.objects.last()
        self.assertIsNotNone(event)
        self.assertLessEqual(len(event.url), 2048)
        self.assertLessEqual(len(event.query_params or ""), 2048)

    def test_truncation_logs_warning(self):
        logger = logging.getLogger("drf_audit_trail.truncation")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        long_url = "/api/test/" + ("a" * 3000)
        client = Client()
        client.get(long_url)
        handler.flush()
        log_output = stream.getvalue()
        logger.removeHandler(handler)
        self.assertIn("Truncating value for field", log_output)


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
