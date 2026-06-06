from .support import *


@override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_SUPPLIER_SETTINGS)
class SupplierAdminAuditExampleTestCase(TransactionTestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(username="supplier-admin")
        self.client.force_login(self.user)
        with disable_manager_audit():
            self.supplier = Supplier.objects.create(
                name="Supplier 1",
                contact_email="supplier@example.com",
                phone="555-0100",
                notes="Primary supplier",
            )

    def test_supplier_admin_should_audit_created_object_with_request(self):
        response = self.client.post(
            reverse("admin:core_supplier_add"),
            data={
                "name": "Admin Supplier",
                "contact_email": "admin-supplier@example.com",
                "phone": "555-0120",
                "notes": "Created in admin",
                "_save": "Save",
            },
        )

        supplier = Supplier.objects.get(contact_email="admin-supplier@example.com")
        entry = AuditLogEntry.objects.get(
            event_type="Create",
            object_id=str(supplier.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entry.action_description, "Created supplier")
        self.assertEqual(entry.request.url, "/admin/core/supplier/add/")
        self.assertEqual(entry.actor_identifier, str(self.user.pk))
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)

    def test_supplier_admin_should_audit_changed_object_with_request(self):
        response = self.client.post(
            reverse("admin:core_supplier_change", args=[self.supplier.pk]),
            data={
                "name": self.supplier.name,
                "contact_email": "supplier-updated@example.com",
                "phone": "555-0199",
                "notes": self.supplier.notes,
                "reason_for_change": "Admin contact correction",
                "_save": "Save",
            },
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.supplier.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(entry.request is not None for entry in entries))
        self.assertEqual(
            entries.get(field_name="contact_email").reason_for_change,
            "Admin contact correction",
        )
        self.assertEqual(
            entries.get(field_name="phone").actor_identifier,
            str(self.user.pk),
        )

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            "enabled": True,
            "models": {},
        }
    )
    def test_supplier_admin_should_audit_without_model_config_when_using_audited_model(
        self,
    ):
        response = self.client.post(
            reverse("admin:core_supplier_change", args=[self.supplier.pk]),
            data={
                "name": self.supplier.name,
                "contact_email": "supplier-default@example.com",
                "phone": "555-0198",
                "notes": self.supplier.notes,
                "_save": "Save",
            },
        )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.supplier.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(entry.request is not None for entry in entries))
        self.assertCountEqual(
            entries.values_list("field_name", flat=True),
            ["contact_email", "phone"],
        )
        self.assertEqual(
            entries.get(field_name="contact_email").action_description,
            "Updated object",
        )

    def test_supplier_admin_should_audit_deleted_object_with_request(self):
        supplier_id = self.supplier.pk

        response = self.client.post(
            reverse("admin:core_supplier_delete", args=[supplier_id]),
            data={
                "post": "yes",
                "reason_for_change": "Admin supplier cleanup",
            },
        )

        entry = AuditLogEntry.objects.get(
            event_type="Delete",
            object_id=str(supplier_id),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entry.action_description, "Deleted supplier")
        self.assertEqual(
            entry.request.url,
            f"/admin/core/supplier/{supplier_id}/delete/",
        )
        self.assertIsNone(entry.reason_for_change)
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)


