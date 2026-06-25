from .support import *
from drf_audit_trail.utils import get_global_audit_actor_role


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

        request = self.request_factory.patch(
            f"/api/product/{self.product.pk}/",
            data={},
            content_type="application/json",
        )
        request.user = user
        request_audit_event = RequestAuditEvent.objects.create(
            method="PATCH",
            url=f"/api/product/{self.product.pk}/",
            ip_addresses="127.0.0.1",
        )

        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(
                request=request,
                request_audit_event=request_audit_event,
                action_description="Updated product with group role",
                model=Product,
            ):
                self.product.name = "Product role update"
                self.product.save(update_fields=["name"])

        entry = AuditLogEntry.objects.get(
            action_description="Updated product with group role"
        )
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

    def test_global_actor_role_getter_should_use_first_group_for_authenticated_user(self):
        user = User.objects.create_user(username="audit-user", password="admin")
        first_group = Group.objects.create(name="Investigator")
        second_group = Group.objects.create(name="Sponsor")
        user.groups.add(first_group, second_group)

        request = self.request_factory.get("/api/product/")
        request.user = user

        self.assertEqual(
            get_global_audit_actor_role(request=request, user=user),
            "Investigator",
        )

    def test_global_actor_role_getter_should_return_anonymous_for_unauthenticated_user(
        self,
    ):
        request = self.request_factory.get("/api/product/")
        request.user = AnonymousUser()

        self.assertEqual(
            get_global_audit_actor_role(request=request),
            "Anonymous",
        )

    def test_global_actor_role_getter_should_return_system_role_for_system_actor(self):
        self.assertEqual(
            get_global_audit_actor_role(actor_type="System"),
            "System",
        )
