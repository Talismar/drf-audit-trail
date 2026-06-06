from .support import *


class ProductAPIManagerAuditExampleTestCase(TransactionTestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.client = Client()
        with disable_manager_audit():
            self.product = Product.objects.create(
                name="Product 1",
                code="product-1",
                price="10.00",
                quantity=1,
            )

    def test_product_api_examples_should_use_manager_audit(self):
        create_response = self.client.post(
            "/api/product/",
            data={
                "name": "Product 2",
                "code": "product-2",
                "price": "20.00",
                "quantity": 2,
                "reason_for_change": "Ignored on create",
            },
            content_type="application/json",
        )
        product = Product.objects.get(code="product-2")

        update_response = self.client.patch(
            f"/api/product/{self.product.pk}/",
            data={
                "price": "12.00",
                "quantity": 2,
                "reason_for_change": "Example correction",
            },
            content_type="application/json",
        )
        price_response = self.client.patch(
            f"/api/product/{self.product.pk}/update-price/",
            data={
                "price": "13.00",
                "reason_for_change": "Price-only correction",
            },
            content_type="application/json",
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(price_response.status_code, 200)

        create_entry = AuditLogEntry.objects.get(
            event_type="Create",
            object_id=str(product.pk),
        )
        self.assertEqual(create_entry.action_description, "Created product through API")
        self.assertIsNone(create_entry.field_name)

        update_entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.product.pk),
            reason_for_change="Example correction",
        )
        self.assertEqual(update_entries.count(), 2)
        self.assertTrue(
            all(
                entry.action_description == "Updated product through API"
                for entry in update_entries
            )
        )

        price_entry = AuditLogEntry.objects.get(
            event_type="Update",
            object_id=str(self.product.pk),
            field_name="price",
            reason_for_change="Price-only correction",
        )
        self.assertEqual(
            price_entry.action_description,
            "Updated product price through API",
        )
        self.assertEqual(
            deserialize_audit_value(price_entry.extra_informations)["request_path"],
            f"/api/product/{self.product.pk}/update-price/",
        )


class SupplierAPIExampleTestCase(TransactionTestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.client = Client()
        with disable_manager_audit():
            self.supplier = Supplier.objects.create(
                name="Supplier 1",
                contact_email="supplier@example.com",
                phone="555-0100",
                notes="Primary supplier",
            )

    def test_supplier_viewset_create_should_not_apply_reason(self):
        response = self.client.post(
            "/api/suppliers/",
            data={
                "name": "API Supplier",
                "contact_email": "api-supplier@example.com",
                "phone": "555-0110",
                "notes": "Created through API",
                "reason_for_change": "Ignored on create",
            },
            content_type="application/json",
        )

        supplier = Supplier.objects.get(contact_email="api-supplier@example.com")
        entry = AuditLogEntry.objects.get(
            event_type="Create",
            object_id=str(supplier.pk),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(entry.action_description, "Created supplier through API")
        self.assertIsNone(entry.reason_for_change)
        self.assertEqual(entry.request.url, "/api/suppliers/")
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)

    def test_supplier_viewset_update_should_audit_each_changed_field(self):
        response = self.client.patch(
            f"/api/suppliers/{self.supplier.pk}/",
            data={
                "contact_email": "supplier-updated@example.com",
                "phone": "555-0199",
                "reason_for_change": "Updated support contact",
            },
            content_type="application/json",
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.supplier.pk),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(entry.request is not None for entry in entries))
        self.assertTrue(
            all(
                entry.action_description == "Updated supplier through API"
                for entry in entries
            )
        )
        self.assertTrue(
            all(
                entry.reason_for_change == "Updated support contact"
                for entry in entries
            )
        )
        self.assertCountEqual(
            entries.values_list("field_name", flat=True),
            ["contact_email", "phone"],
        )

    def test_supplier_viewset_destroy_should_apply_reason_and_payload(self):
        supplier_id = self.supplier.pk

        response = self.client.delete(
            f"/api/suppliers/{supplier_id}/",
            data=json.dumps({"reason_for_change": "Supplier no longer active"}),
            content_type="application/json",
        )

        entry = AuditLogEntry.objects.get(
            event_type="Delete",
            object_id=str(supplier_id),
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(entry.action_description, "Deleted supplier through API")
        self.assertEqual(entry.reason_for_change, "Supplier no longer active")
        self.assertIsNotNone(entry.request)
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)

    def test_supplier_custom_action_should_audit_notes_only(self):
        response = self.client.post(
            f"/api/suppliers/{self.supplier.pk}/update-notes/",
            data={
                "notes": "Preferred supplier after review",
                "reason_for_change": "Review completed",
            },
            content_type="application/json",
        )

        entry = AuditLogEntry.objects.get(
            event_type="Update",
            object_id=str(self.supplier.pk),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(entry.field_name, "notes")
        self.assertEqual(entry.action_description, "Updated supplier notes")
        self.assertEqual(entry.reason_for_change, "Review completed")
        self.assertEqual(
            entry.new_values_data,
            "Preferred supplier after review",
        )
