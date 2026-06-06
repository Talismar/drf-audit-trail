from .support import *


@override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_SUPPLIER_SETTINGS)
class SupplierManagerAuditExampleTestCase(TestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        with disable_manager_audit():
            self.supplier = Supplier.objects.create(
                name="Supplier 1",
                contact_email="supplier@example.com",
                phone="555-0100",
                notes="Primary supplier",
            )

    def test_supplier_create_should_create_one_object_level_entry(self):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(reason_for_change="Initial supplier load"):
                supplier = Supplier.objects.create(
                    name="Supplier 2",
                    contact_email="supplier-2@example.com",
                    phone="555-0102",
                    notes="Backup supplier",
                )

        entry = AuditLogEntry.objects.get(
            event_type="Create",
            object_id=str(supplier.pk),
        )

        self.assertEqual(entry.action_description, "Created supplier")
        self.assertEqual(entry.content_type, "core.supplier")
        self.assertEqual(entry.reason_for_change, "Initial supplier load")
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)

    def test_supplier_update_should_create_one_entry_per_changed_tracked_field(self):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(reason_for_change="Contact correction"):
                Supplier.objects.filter(pk=self.supplier.pk).update(
                    contact_email="supplier-updated@example.com",
                    phone="555-0199",
                )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.supplier.pk),
        )

        self.assertEqual(entries.count(), 2)
        self.assertCountEqual(
            entries.values_list("field_name", flat=True),
            ["contact_email", "phone"],
        )
        self.assertEqual(
            entries.get(field_name="contact_email").old_values_data,
            "supplier@example.com",
        )
        self.assertEqual(
            entries.get(field_name="phone").new_values_data,
            "555-0199",
        )

    def test_supplier_delete_should_create_one_object_level_entry(self):
        supplier_id = self.supplier.pk

        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(reason_for_change="Supplier cleanup"):
                self.supplier.delete()

        entry = AuditLogEntry.objects.get(
            event_type="Delete",
            object_id=str(supplier_id),
        )

        self.assertEqual(entry.action_description, "Deleted supplier")
        self.assertEqual(entry.reason_for_change, "Supplier cleanup")
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)

    def test_supplier_context_should_override_fields_and_action_description(self):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(
                reason_for_change="Notes review",
                action_description="Updated supplier notes",
                models={"core.Supplier": {"fields": ["notes"]}},
            ):
                Supplier.objects.filter(pk=self.supplier.pk).update(
                    phone="555-0177",
                    notes="Preferred after review",
                )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.supplier.pk),
        )

        self.assertEqual(entries.count(), 1)
        entry = entries.get()
        self.assertEqual(entry.field_name, "notes")
        self.assertEqual(entry.action_description, "Updated supplier notes")
        self.assertEqual(entry.reason_for_change, "Notes review")


class AuditModelContextReferenceTestCase(TestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        with disable_manager_audit():
            self.supplier = Supplier.objects.create(
                name="Supplier 1",
                contact_email="supplier@example.com",
                phone="555-0100",
                notes="Primary supplier",
            )

    def test_model_reference_should_enable_audit_and_track_default_fields(self):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(
                model=Supplier,
                reason_for_change="Supplier details review",
            ):
                Supplier.objects.filter(pk=self.supplier.pk).update(
                    name="Supplier 1 updated",
                    contact_email="supplier-updated@example.com",
                    phone="555-0199",
                    notes="Preferred supplier",
                )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.supplier.pk),
        )

        self.assertEqual(entries.count(), 4)
        self.assertCountEqual(
            entries.values_list("field_name", flat=True),
            ["name", "contact_email", "phone", "notes"],
        )
        self.assertFalse(entries.filter(field_name="created_at").exists())
        self.assertFalse(entries.filter(field_name="updated_at").exists())

    def test_instance_reference_should_accept_field_override(self):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(
                model=self.supplier,
                fields=["notes"],
                reason_for_change="Supplier note review",
            ):
                Supplier.objects.filter(pk=self.supplier.pk).update(
                    phone="555-0177",
                    notes="Preferred after review",
                )

        entry = AuditLogEntry.objects.get(
            event_type="Update",
            object_id=str(self.supplier.pk),
        )

        self.assertEqual(entry.field_name, "notes")
        self.assertEqual(entry.reason_for_change, "Supplier note review")

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            "enabled": True,
            "models": {"core.Supplier": {}},
        }
    )
    def test_empty_model_config_should_track_default_fields(self):
        with self.captureOnCommitCallbacks(execute=True):
            Supplier.objects.filter(pk=self.supplier.pk).update(
                phone="555-0199",
                notes="Reviewed supplier",
            )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.supplier.pk),
        )

        self.assertEqual(entries.count(), 2)
        self.assertCountEqual(
            entries.values_list("field_name", flat=True),
            ["phone", "notes"],
        )


