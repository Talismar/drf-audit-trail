import io
import logging
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.models import Product
from drf_audit_trail.audit_log import audit_log, record_system_event
from drf_audit_trail.middleware.request_login_audit_event import (
    RequestLoginAuditEventMiddleware,
)
from drf_audit_trail.models import (
    AuditLogEntry,
    LoginAuditEvent,
    ProcessAuditEvent,
    RequestAuditEvent,
)
from drf_audit_trail.utils import deserialize_audit_value


def get_custom_test_user_role(user, request=None):
    return f"custom:{user.username}"


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


class AuditLogEntryTestCase(TestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.request_factory = RequestFactory()
        self.product = Product.objects.create(
            name="Product 1",
            code="product-1",
            price="10.00",
            quantity=1,
        )

    def test_audit_log_decorator_should_create_entry_linked_to_request(self):
        @audit_log(
            event_type="Update",
            action_description="Updated product price",
            field_name="price",
        )
        def view(request, audit_log):
            audit_log.set_content_object(self.product)
            audit_log.actor_role = "Site User"
            audit_log.old_values = {"price": "10.00"}
            audit_log.new_values = {"price": "12.00"}
            audit_log.reason_for_change = "Correction after review"
            audit_log.extra_informations = {"source": "unit-test"}
            return HttpResponse("ok")

        request = self.request_factory.patch(
            "/admin/jsi18n/",
            data={},
            content_type="application/json",
        )
        request.user = AnonymousUser()

        response = RequestLoginAuditEventMiddleware(view).process_request(request)

        self.assertEqual(response.status_code, 200)

        entry = AuditLogEntry.objects.get()
        self.assertIsNotNone(entry.request)
        self.assertEqual(entry.request.url, "/admin/jsi18n/")
        self.assertEqual(entry.event_type, "Update")
        self.assertEqual(entry.action_description, "Updated product price")
        self.assertEqual(entry.actor_role, "Site User")
        self.assertEqual(entry.content_type, "core.product")
        self.assertEqual(entry.object_id, str(self.product.pk))
        self.assertEqual(entry.object_repr, str(self.product))
        self.assertEqual(entry.get_content_object(), self.product)
        self.assertEqual(entry.old_values_data, {"price": "10.00"})
        self.assertEqual(entry.new_values_data, {"price": "12.00"})
        self.assertEqual(entry.reason_for_change, "Correction after review")
        self.assertEqual(
            deserialize_audit_value(entry.extra_informations),
            {"source": "unit-test"},
        )

    def test_audit_log_decorator_should_find_request_on_bound_method(self):
        user = User.objects.create_user(username="perform-update-user")
        product = self.product

        class Serializer:
            def save(self):
                product.name = "Product 1 updated"
                product.save(update_fields=["name"])
                return Product.objects.get(pk=product.pk)

        class ProductUpdateView:
            def __init__(self, request):
                self.request = request

            def get_object(self):
                return Product.objects.get(pk=product.pk)

            @audit_log(
                event_type="Update",
                action_description="Updated product",
                field_name="name",
            )
            def perform_update(self, serializer, audit_log):
                old_instance = self.get_object()
                audit_log.set_content_object(old_instance)

                updated_instance = serializer.save()

                audit_log.old_values = old_instance.name
                audit_log.new_values = updated_instance.name
                audit_log.reason_for_change = "Product name changed"

        def view(request):
            ProductUpdateView(request).perform_update(Serializer())
            return HttpResponse("ok")

        request = self.request_factory.patch(
            "/api/product/1/",
            data={},
            content_type="application/json",
        )
        request.user = user

        response = RequestLoginAuditEventMiddleware(view).process_request(request)

        entry = AuditLogEntry.objects.get(action_description="Updated product")

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(entry.request)
        self.assertEqual(entry.actor_identifier, str(user.pk))
        self.assertEqual(entry.old_values_data, "Product 1")
        self.assertEqual(entry.new_values_data, "Product 1 updated")
        self.assertEqual(entry.reason_for_change, "Product name changed")

    def test_audit_log_context_should_create_one_entry_per_field_change(self):
        @audit_log(
            event_type="Update",
            action_description="Updated product",
        )
        def view(request, audit_log):
            audit_log.set_content_object(self.product)
            audit_log.add_field_change(
                field_name="price",
                old_values={"price": "10.00"},
                new_values={"price": "12.00"},
                reason_for_change="Correction after price review",
            )
            audit_log.add_field_change(
                field_name="quantity",
                old_values={"quantity": 1},
                new_values={"quantity": 2},
                reason_for_change="Correction after stock review",
            )
            return HttpResponse("ok")

        request = self.request_factory.patch(
            "/api/product/1/",
            data={},
            content_type="application/json",
        )
        request.user = AnonymousUser()

        RequestLoginAuditEventMiddleware(view).process_request(request)

        entries = AuditLogEntry.objects.order_by("field_name")

        self.assertEqual(entries.count(), 2)
        self.assertEqual(entries[0].field_name, "price")
        self.assertEqual(entries[0].old_values_data, {"price": "10.00"})
        self.assertEqual(entries[0].reason_for_change, "Correction after price review")
        self.assertEqual(entries[1].field_name, "quantity")
        self.assertEqual(entries[1].new_values_data, {"quantity": 2})
        self.assertEqual(entries[1].reason_for_change, "Correction after stock review")

    def test_record_system_event_should_create_entry_without_request(self):
        entry = record_system_event(
            event_type="System Action",
            action_description="Auto-save product",
            actor_identifier="system",
            content_object=self.product,
            field_name="autosaved",
            new_values={"autosaved": True},
        )

        self.assertIsNone(entry.request)
        self.assertEqual(entry.actor_type, AuditLogEntry.SYSTEM)
        self.assertEqual(entry.actor_identifier, "system")
        self.assertEqual(entry.content_type, "core.product")
        self.assertEqual(entry.object_id, str(self.product.pk))
        self.assertEqual(entry.get_content_object(), self.product)
        self.assertEqual(entry.field_name, "autosaved")
        self.assertEqual(entry.new_values_data, {"autosaved": True})
        self.assertIsNone(entry.reason_for_change)

    def test_field_name_should_be_required_when_old_or_new_values_are_set(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Field name is required when old values or new values are set.",
        ):
            record_system_event(
                event_type="System Action",
                action_description="Updated product price",
                content_object=self.product,
                old_values={"price": "10.00"},
                new_values={"price": "12.00"},
                reason_for_change="Correction after review",
            )

    def test_reason_for_change_should_not_be_required_when_only_field_name_is_set(self):
        entry = record_system_event(
            event_type="System Action",
            action_description="Marked product for background review",
            content_object=self.product,
            field_name="review_status",
        )

        self.assertEqual(entry.field_name, "review_status")
        self.assertIsNone(entry.reason_for_change)

    def test_actor_role_should_default_to_first_django_group(self):
        user = User.objects.create_user(username="audit-user", password="admin")
        first_group = Group.objects.create(name="Investigator")
        second_group = Group.objects.create(name="Sponsor")
        user.groups.add(first_group, second_group)

        client = Client()
        client.force_login(user)
        response = client.get(
            f"/audit-log-django-view-products/{self.product.pk}/with-user-role/"
        )

        entry = AuditLogEntry.objects.get(
            action_description="Viewed product using Django view with user role"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(entry.actor_identifier, str(user.pk))
        self.assertEqual(entry.actor_role, "Investigator")

    @override_settings(
        DRF_AUDIT_TRAIL_USER_ROLE_GETTER="drf_audit_trail.tests.get_custom_test_user_role"
    )
    def test_actor_role_should_support_custom_getter_setting(self):
        user = User.objects.create_user(username="custom-role-user", password="admin")

        @audit_log(
            event_type="View",
            action_description="Viewed product with custom role getter",
        )
        def view(request, audit_log):
            audit_log.set_content_object(self.product)
            return HttpResponse("ok")

        request = self.request_factory.get("/api/custom-role/")
        request.user = user

        RequestLoginAuditEventMiddleware(view).process_request(request)

        entry = AuditLogEntry.objects.get(
            action_description="Viewed product with custom role getter"
        )

        self.assertEqual(entry.actor_identifier, str(user.pk))
        self.assertEqual(entry.actor_role, "custom:custom-role-user")

    def test_core_example_views_should_create_audit_log_entries(self):
        client = Client()

        api_view_response = client.get(
            f"/api/audit-log-api-view-products/{self.product.pk}/"
        )
        django_view_response = client.get(
            f"/audit-log-django-view-products/{self.product.pk}/"
        )
        generic_view_response = client.patch(
            f"/api/audit-log-generic-products/{self.product.pk}/",
            data={"price": "12.00", "reason_for_change": "Example correction"},
            content_type="application/json",
        )
        viewset_response = client.post(
            "/api/audit-log-products/",
            data={
                "name": "Product 2",
                "code": "product-2",
                "price": "20.00",
                "quantity": 2,
            },
            content_type="application/json",
        )

        self.assertEqual(api_view_response.status_code, 200)
        self.assertEqual(django_view_response.status_code, 200)
        self.assertEqual(generic_view_response.status_code, 200)
        self.assertEqual(viewset_response.status_code, 201)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action_description="Viewed product using APIView"
            ).exists()
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action_description="Viewed product using Django view"
            ).exists()
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action_description="Updated product using GenericAPIView"
            ).exists()
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action_description="Created product using ModelViewSet"
            ).exists()
        )


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

    @patch("drf_audit_trail.admin.HTML")
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
