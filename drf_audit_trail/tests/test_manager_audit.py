from .support import *


class ManagerAuditTestCase(TestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.product = Product.objects.create(
            name="Product 1",
            code="product-1",
            price="10.00",
            quantity=1,
        )

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_manager_create_should_create_one_entry_per_object(self):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(
                reason_for_change="Initial load",
                actor_identifier="import-job",
            ):
                product = Product.objects.create(
                    name="Product 2",
                    code="product-2",
                    price="20.00",
                    quantity=2,
                )

        entries = AuditLogEntry.objects.filter(
            event_type="Create",
            object_id=str(product.pk),
        )

        entry = entries.get()
        self.assertEqual(entry.action_description, "Created product")
        self.assertEqual(entry.actor_identifier, "import-job")
        self.assertEqual(entry.reason_for_change, "Initial load")
        self.assertEqual(entry.content_type, "core.product")
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_queryset_update_should_compare_old_and_new_values(self):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(reason_for_change="Price and stock correction"):
                Product.objects.filter(pk=self.product.pk).update(
                    price="12.00",
                    quantity=2,
                )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            object_id=str(self.product.pk),
        ).order_by("field_name")

        self.assertEqual(entries.count(), 2)
        self.assertEqual(
            entries.get(field_name="price").old_values_data,
            "10.00",
        )
        self.assertEqual(
            entries.get(field_name="price").new_values_data,
            "12.00",
        )
        self.assertEqual(
            entries.get(field_name="quantity").old_values_data,
            1,
        )
        self.assertEqual(
            entries.get(field_name="quantity").new_values_data,
            2,
        )
        self.assertEqual(
            entries.get(field_name="price").action_description,
            "Product price updated",
        )
        self.assertEqual(
            entries.get(field_name="quantity").action_description,
            "Product quantity updated",
        )

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_queryset_update_should_accept_reason_field_in_kwargs(self):
        with self.captureOnCommitCallbacks(execute=True):
            Product.objects.filter(pk=self.product.pk).update(
                quantity=9,
                reason_for_change="Inline reason",
            )

        entry = AuditLogEntry.objects.get(field_name="quantity")
        self.assertEqual(entry.reason_for_change, "Inline reason")

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_manager_get_or_create_should_audit_created_object(self):
        with self.captureOnCommitCallbacks(execute=True):
            product, created = Product.objects.get_or_create(
                code="product-2",
                defaults={
                    "name": "Product 2",
                    "price": "20.00",
                    "quantity": 2,
                },
            )

        self.assertTrue(created)
        entries = AuditLogEntry.objects.filter(
            event_type="Create",
            object_id=str(product.pk),
        )
        self.assertEqual(entries.count(), 1)
        entry = entries.get()
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_manager_update_or_create_should_audit_existing_object(self):
        with self.captureOnCommitCallbacks(execute=True):
            product, created = Product.objects.update_or_create(
                code="product-1",
                defaults={"quantity": 7},
            )

        self.assertFalse(created)
        entry = AuditLogEntry.objects.get(
            event_type="Update",
            object_id=str(product.pk),
            field_name="quantity",
        )
        self.assertEqual(entry.old_values_data, 1)
        self.assertEqual(entry.new_values_data, 7)

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_model_save_should_audit_instance_update(self):
        self.product.price = "13.00"

        with self.captureOnCommitCallbacks(execute=True):
            self.product.save(update_fields=["price"])

        entry = AuditLogEntry.objects.get(
            event_type="Update",
            object_id=str(self.product.pk),
            field_name="price",
        )
        self.assertEqual(entry.old_values_data, "10.00")
        self.assertEqual(entry.new_values_data, "13.00")

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_model_delete_should_audit_instance_delete(self):
        product_id = self.product.pk

        with self.captureOnCommitCallbacks(execute=True):
            self.product.delete()

        entries = AuditLogEntry.objects.filter(
            event_type="Delete",
            object_id=str(product_id),
        )

        self.assertEqual(entries.count(), 1)
        entry = entries.get()
        self.assertEqual(entry.action_description, "Deleted product")
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audit_model_context_should_override_fields_and_action_description(self):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(
                reason_for_change="Consensus update",
                action_description="Updated consensus during review",
                models={"core.Product": {"fields": ["quantity"]}},
            ):
                Product.objects.filter(pk=self.product.pk).update(
                    price="12.00",
                    quantity=2,
                )

        entries = AuditLogEntry.objects.filter(object_id=str(self.product.pk))

        self.assertEqual(entries.count(), 1)
        entry = entries.get()
        self.assertEqual(entry.field_name, "quantity")
        self.assertEqual(entry.action_description, "Updated consensus during review")
        self.assertEqual(entry.reason_for_change, "Consensus update")

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_field_update_action_description_should_fallback_when_field_is_missing(
        self,
    ):
        with patch.object(
            Product,
            "FIELD_UPDATE_ACTION_DESCRIPTIONS",
            {"price": "Product price updated"},
        ):
            with self.captureOnCommitCallbacks(execute=True):
                Product.objects.filter(pk=self.product.pk).update(quantity=2)

        entry = AuditLogEntry.objects.get(field_name="quantity")
        self.assertEqual(entry.action_description, "Updated product")

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_field_update_action_description_should_ignore_empty_value(self):
        with patch.object(
            Product,
            "FIELD_UPDATE_ACTION_DESCRIPTIONS",
            {"quantity": ""},
        ):
            with self.captureOnCommitCallbacks(execute=True):
                Product.objects.filter(pk=self.product.pk).update(quantity=2)

        entry = AuditLogEntry.objects.get(field_name="quantity")
        self.assertEqual(entry.action_description, "Updated product")

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            **MANAGER_AUDIT_PRODUCT_SETTINGS,
            "models": {
                "core.Product": {
                    **MANAGER_AUDIT_PRODUCT_SETTINGS["models"]["core.Product"],
                    "require_reason": True,
                }
            },
        }
    )
    def test_required_reason_should_block_mutation_before_update(self):
        with self.assertRaisesMessage(
            ValidationError,
            "reason_for_change is required for audited changes.",
        ):
            Product.objects.filter(pk=self.product.pk).update(price="12.00")

        self.product.refresh_from_db()
        self.assertEqual(str(self.product.price), "10.00")
        self.assertEqual(AuditLogEntry.objects.count(), 0)

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_disable_manager_audit_should_skip_entries(self):
        with self.captureOnCommitCallbacks(execute=True):
            with disable_manager_audit():
                Product.objects.filter(pk=self.product.pk).update(price="12.00")

        self.assertEqual(AuditLogEntry.objects.count(), 0)

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_set_audit_reason_should_apply_inside_current_context(self):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context():
                set_audit_reason("Reason set later")
                Product.objects.filter(pk=self.product.pk).update(quantity=3)

        entry = AuditLogEntry.objects.get(field_name="quantity")
        self.assertEqual(entry.reason_for_change, "Reason set later")

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audit_model_context_should_use_request_audit_event_when_available(self):
        user = User.objects.create_user(username="manager-audit-user")
        request = RequestFactory().patch("/api/products/1/")
        request.user = user
        request_audit_event = RequestAuditEvent.objects.create(
            method="PATCH",
            url="/api/products/1/",
            ip_addresses="127.0.0.1",
        )

        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(
                request=request,
                request_audit_event=request_audit_event,
            ):
                Product.objects.filter(pk=self.product.pk).update(quantity=4)

        entry = AuditLogEntry.objects.get(field_name="quantity")
        self.assertEqual(entry.actor_identifier, str(user.pk))
        self.assertEqual(entry.request, request_audit_event)

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_queryset_delete_should_audit_object_without_field_values(self):
        product_id = self.product.pk

        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(reason_for_change="Cleanup"):
                Product.objects.filter(pk=product_id).delete()

        entries = AuditLogEntry.objects.filter(
            event_type="Delete",
            object_id=str(product_id),
        )

        self.assertEqual(entries.count(), 1)
        entry = entries.get()
        self.assertIsNone(entry.field_name)
        self.assertIsNone(entry.old_values_data)
        self.assertIsNone(entry.new_values_data)
        self.assertEqual(entry.reason_for_change, "Cleanup")

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_queryset_bulk_create_should_audit_objects_without_field_values(
        self,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            products = Product.objects.bulk_create(
                [
                    Product(
                        name="Bulk 1",
                        code="bulk-1",
                        price="30.00",
                        quantity=3,
                    ),
                    Product(
                        name="Bulk 2",
                        code="bulk-2",
                        price="40.00",
                        quantity=4,
                    ),
                ]
            )

        entries = AuditLogEntry.objects.filter(event_type="Create")

        self.assertEqual(entries.count(), 2)
        first_entry = entries.get(object_id=str(products[0].pk))
        second_entry = entries.get(object_id=str(products[1].pk))
        self.assertIsNone(first_entry.field_name)
        self.assertIsNone(first_entry.old_values_data)
        self.assertIsNone(first_entry.new_values_data)
        self.assertIsNone(second_entry.field_name)
        self.assertIsNone(second_entry.old_values_data)
        self.assertIsNone(second_entry.new_values_data)

    @override_settings(DRF_AUDIT_TRAIL_MANAGER_AUDIT=MANAGER_AUDIT_PRODUCT_SETTINGS)
    def test_audited_queryset_bulk_update_should_compare_old_and_new_values(self):
        second_product = Product.objects.create(
            name="Product 2",
            code="product-2",
            price="20.00",
            quantity=2,
        )
        self.product.quantity = 5
        second_product.quantity = 6

        with self.captureOnCommitCallbacks(execute=True):
            Product.objects.bulk_update(
                [self.product, second_product],
                ["quantity"],
            )

        entries = AuditLogEntry.objects.filter(
            event_type="Update",
            field_name="quantity",
        )

        self.assertEqual(entries.count(), 2)
        self.assertEqual(
            entries.get(object_id=str(self.product.pk)).new_values_data,
            5,
        )
        self.assertEqual(
            entries.get(object_id=str(second_product.pk)).new_values_data,
            6,
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
    def test_audited_model_should_audit_without_explicit_model_config(self):
        with self.captureOnCommitCallbacks(execute=True):
            Product.objects.filter(pk=self.product.pk).update(quantity=8)

        entry = AuditLogEntry.objects.get(field_name="quantity")
        self.assertEqual(entry.action_description, "Product quantity updated")

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            **MANAGER_AUDIT_PRODUCT_SETTINGS,
            "default_extra_informations_getter": (
                "drf_audit_trail.tests.get_manager_audit_extra_informations"
            ),
        }
    )
    def test_default_extra_informations_getter_should_apply_to_update_entries(self):
        with self.captureOnCommitCallbacks(execute=True):
            Product.objects.filter(pk=self.product.pk).update(quantity=8)

        entry = AuditLogEntry.objects.get(field_name="quantity")
        extra_informations = deserialize_audit_value(entry.extra_informations)

        self.assertEqual(
            extra_informations,
            {
                "scope": "core.product",
                "object_id": self.product.pk,
                "action": "update",
                "field_name": "quantity",
                "old_raw_value": 1,
                "new_raw_value": 8,
            },
        )

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            **MANAGER_AUDIT_PRODUCT_SETTINGS,
            "default_extra_informations_getter": (
                "drf_audit_trail.tests.get_manager_audit_extra_informations"
            ),
        }
    )
    def test_default_extra_informations_getter_should_apply_to_create_and_delete(self):
        with self.captureOnCommitCallbacks(execute=True):
            product = Product.objects.create(
                name="Product 2",
                code="product-2",
                price="20.00",
                quantity=2,
            )

        create_entry = AuditLogEntry.objects.get(
            event_type="Create",
            object_id=str(product.pk),
        )
        create_extra_informations = deserialize_audit_value(
            create_entry.extra_informations
        )
        product_id = product.pk

        with self.captureOnCommitCallbacks(execute=True):
            product.delete()

        delete_entry = AuditLogEntry.objects.get(
            event_type="Delete",
            object_id=str(product_id),
        )
        delete_extra_informations = deserialize_audit_value(
            delete_entry.extra_informations
        )

        self.assertEqual(
            create_extra_informations,
            {
                "scope": "core.product",
                "object_id": product_id,
                "action": "create",
            },
        )
        self.assertEqual(
            delete_extra_informations,
            {
                "scope": "core.product",
                "object_id": product_id,
                "action": "delete",
            },
        )

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            **MANAGER_AUDIT_PRODUCT_SETTINGS,
            "default_extra_informations_getter": (
                "drf_audit_trail.tests.get_manager_audit_extra_informations"
            ),
            "models": {
                "core.Product": {
                    **MANAGER_AUDIT_PRODUCT_SETTINGS["models"]["core.Product"],
                    "extra_informations_getter": (
                        "drf_audit_trail.tests."
                        "get_manager_audit_model_extra_informations"
                    ),
                }
            },
        }
    )
    def test_model_extra_informations_getter_should_override_global_and_merge_context(
        self,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            with audit_model_context(
                extra_informations={"source": "view", "scope": "context"},
            ):
                Product.objects.filter(pk=self.product.pk).update(quantity=8)

        entry = AuditLogEntry.objects.get(field_name="quantity")
        extra_informations = deserialize_audit_value(entry.extra_informations)

        self.assertEqual(
            extra_informations,
            {
                "scope": "context",
                "object_id": self.product.pk,
                "action": "update",
                "model_getter": True,
                "source": "view",
            },
        )

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            **MANAGER_AUDIT_PRODUCT_SETTINGS,
            "default_value_serializer": "text",
        }
    )
    def test_default_value_serializer_should_allow_text_output(self):
        with self.captureOnCommitCallbacks(execute=True):
            Product.objects.filter(pk=self.product.pk).update(name="Product text mode")

        entry = AuditLogEntry.objects.get(field_name="name")
        self.assertEqual(entry.old_values_data, "Product 1")
        self.assertEqual(entry.new_values_data, "Product text mode")

    @override_settings(
        DRF_AUDIT_TRAIL_MANAGER_AUDIT={
            **MANAGER_AUDIT_PRODUCT_SETTINGS,
            "models": {
                "core.Product": {
                    **MANAGER_AUDIT_PRODUCT_SETTINGS["models"]["core.Product"],
                    "field_value_serializers": {"quantity": "pk_and_repr"},
                }
            },
        }
    )
    def test_field_value_serializers_should_allow_per_field_override(self):
        with self.captureOnCommitCallbacks(execute=True):
            Product.objects.filter(pk=self.product.pk).update(
                price="12.00",
                quantity=22,
            )

        quantity_entry = AuditLogEntry.objects.get(field_name="quantity")
        price_entry = AuditLogEntry.objects.get(field_name="price")

        self.assertEqual(
            quantity_entry.new_values_data,
            {"pk": "22", "repr": "22"},
        )
        self.assertEqual(price_entry.new_values_data, "12.00")


