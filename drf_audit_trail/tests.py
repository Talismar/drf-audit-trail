from django.contrib.auth.models import User
from django.test import Client, TestCase

from drf_audit_trail.models import LoginAuditEvent, RequestAuditEvent


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
