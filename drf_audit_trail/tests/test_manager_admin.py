from .support import *


class ManagerAuditDefaultAdminRequestTestCase(TransactionTestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(username="default-product-admin")
        self.client.force_login(self.user)
        with disable_manager_audit():
            self.product = Product.objects.create(
                name="Product 1",
                code="product-1",
                price="10.00",
                quantity=1,
            )

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            "enabled": True,
            "default_fields": "__all__",
            "default_exclude_fields": ["created_at", "updated_at"],
            "default_action_descriptions": {
                "create": "Created object",
                "update": "Updated object",
                "delete": "Deleted object",
            },
            "models": {},
        }
    )
    def test_audited_model_should_cover_product_admin_update_without_model_config(self):
        response = self.client.post(
            reverse("admin:core_product_change", args=[self.product.pk]),
            data={
                "name": self.product.name,
                "code": self.product.code,
                "price": "12.00",
                "quantity": 2,
                "reason_for_change": "Default admin correction",
                "_save": "Save",
            },
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.product.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(entry.request is not None for entry in entries))
        self.assertCountEqual(
            entries.values_list("field_name", flat=True),
            ["price", "quantity"],
        )
        self.assertEqual(
            entries.get(field_name="price").action_description,
            "Product price updated",
        )
        self.assertEqual(
            entries.get(field_name="quantity").reason_for_change,
            "Default admin correction",
        )
        self.assertEqual(
            entries.get(field_name="quantity").actor_identifier,
            str(self.user.pk),
        )

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            "enabled": True,
            "models": {
                "core.Product": {
                    "default_reason": "Changed by audited model fallback",
                }
            },
        }
    )
    def test_request_reason_should_apply_before_default_reason(self):
        response = self.client.post(
            reverse("admin:core_product_change", args=[self.product.pk]),
            data={
                "name": self.product.name,
                "code": self.product.code,
                "price": "12.00",
                "quantity": 2,
                "reason_for_change": "Ignored admin POST reason",
                "_save": "Save",
            },
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.product.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(entry.request is not None for entry in entries))
        self.assertTrue(
            all(
                entry.reason_for_change == "Ignored admin POST reason"
                for entry in entries
            )
        )

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            "enabled": True,
            "reason_for_change_key": "custom_reason",
            "models": {},
        }
    )
    def test_admin_update_should_use_custom_global_request_reason_key(self):
        response = self.client.post(
            reverse("admin:core_product_change", args=[self.product.pk]),
            data={
                "name": self.product.name,
                "code": self.product.code,
                "price": "12.00",
                "quantity": 2,
                "custom_reason": "Custom admin reason",
                "_save": "Save",
            },
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.product.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(
            all(entry.reason_for_change == "Custom admin reason" for entry in entries)
        )

    def test_admin_update_should_parse_json_object_reason_from_post(self):
        response = self.client.post(
            reverse("admin:core_product_change", args=[self.product.pk]),
            data={
                "name": self.product.name,
                "code": self.product.code,
                "price": "12.00",
                "quantity": 2,
                "reason_for_change": json.dumps(
                    {
                        "price": "Admin price review",
                        "quantity": "Admin stock review",
                    }
                ),
                "_save": "Save",
            },
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.product.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entries.count(), 2)
        self.assertEqual(
            entries.get(field_name="price").reason_for_change,
            "Admin price review",
        )
        self.assertEqual(
            entries.get(field_name="quantity").reason_for_change,
            "Admin stock review",
        )

    def test_api_json_update_should_use_request_body_reason(self):
        response = self.client.patch(
            f"/api/product/{self.product.pk}/",
            data=json.dumps(
                {
                    "price": "12.00",
                    "quantity": 2,
                    "reason_for_change": "API body reason",
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.user)}",
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.product.pk),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(
            all(entry.reason_for_change == "API body reason" for entry in entries)
        )

    def test_api_json_update_should_apply_reason_by_field(self):
        response = self.client.patch(
            f"/api/product/{self.product.pk}/",
            data=json.dumps(
                {
                    "price": "12.00",
                    "quantity": 2,
                    "reason_for_change": {
                        "price": "Price review",
                        "quantity": "Stock review",
                    },
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.user)}",
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.product.pk),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(entries.count(), 2)
        self.assertEqual(
            entries.get(field_name="price").reason_for_change,
            "Price review",
        )
        self.assertEqual(
            entries.get(field_name="quantity").reason_for_change,
            "Stock review",
        )

    def test_context_reason_should_win_over_request_reason(self):
        request = RequestFactory().post(
            "/api/product/",
            data={"reason_for_change": "Request reason"},
        )
        request.user = self.user
        request_audit_event = RequestAuditEvent.objects.create(
            method="POST",
            url="/api/product/",
            ip_addresses="127.0.0.1",
        )

        with audit_model_context(
            request=request,
            request_audit_event=request_audit_event,
            reason_for_change="Context reason",
        ):
            Product.objects.filter(pk=self.product.pk).update(quantity=2)

        entry = AuditLogEntry.objects.get(field_name="quantity")
        self.assertEqual(entry.reason_for_change, "Context reason")


@override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
class ManagerAuditAdminRequestTestCase(TransactionTestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.client = Client()
        self.product = Product.objects.create(
            name="Product 1",
            code="product-1",
            price="10.00",
            quantity=1,
        )

    def test_audited_model_admin_should_audit_created_object_with_request(self):
        user = User.objects.create_superuser(username="product-admin")
        self.client.force_login(user)

        response = self.client.post(
            reverse("admin:core_product_add"),
            data={
                "name": "Admin Product",
                "code": "admin-product",
                "price": "15.00",
                "quantity": 3,
                "_save": "Save",
            },
        )

        product = Product.objects.get(code="admin-product")
        entries = AuditLogEntry.objects.filter(
            event_type="Create",
            object_id=str(product.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entries.count(), 1)
        self.assertTrue(all(entry.request is not None for entry in entries))
        entry = entries.get()
        self.assertEqual(
            entry.actor_identifier,
            str(user.pk),
        )
        self.assertEqual(
            entry.request.url,
            "/admin/core/product/add/",
        )
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)

    def test_audited_model_admin_should_audit_changed_object_with_request(self):
        user = User.objects.create_superuser(username="product-change-admin")
        self.client.force_login(user)

        response = self.client.post(
            reverse("admin:core_product_change", args=[self.product.pk]),
            data={
                "name": self.product.name,
                "code": self.product.code,
                "price": "12.00",
                "quantity": 2,
                "reason_for_change": "Admin correction",
                "_save": "Save",
            },
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.product.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(entry.request is not None for entry in entries))
        self.assertEqual(
            entries.get(field_name="price").reason_for_change,
            "Admin correction",
        )
        self.assertEqual(
            entries.get(field_name="quantity").actor_identifier,
            str(user.pk),
        )

    def test_audited_model_admin_should_audit_deleted_object_with_request(self):
        user = User.objects.create_superuser(username="product-delete-admin")
        self.client.force_login(user)
        product_id = self.product.pk

        response = self.client.post(
            reverse("admin:core_product_delete", args=[product_id]),
            data={
                "post": "yes",
                "reason_for_change": "Admin cleanup",
            },
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Delete",
            object_id=str(product_id),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entries.count(), 1)
        self.assertTrue(all(entry.request is not None for entry in entries))
        entry = entries.get()
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)
        self.assertIsNone(entry.reason_for_change)


