import importlib
import uuid
from io import StringIO
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import call, patch

from django.contrib import admin
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import (
    Client,
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse
from django.views import View
from rest_framework.decorators import action
from rest_framework.generics import ListCreateAPIView
from rest_framework.mixins import CreateModelMixin
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ViewSet

from core.audit import get_pg_audit_extra_informations
from core.models import Category, Product
from drf_audit_trail.settings import DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE

from . import (
    ACTOR_ROLE_SETTING,
    ACTOR_TYPE_SETTING,
    REASON_FOR_CHANGE_SETTING,
    SOURCE_SETTING,
    USER_SETTING,
    audit,
    call_with_supported_kwargs,
    deserialize_extra_informations,
    deserialize_reason_for_change,
    get_pg_audit_config,
    merge_extra_informations,
    normalize_reason_for_model_columns,
    serialize_extra_informations,
    system_audit,
)
from .admin import ActionLogAdmin
from .config import (
    get_api_views_module_paths,
    get_audited_model_tables,
    get_django_views_module_paths,
    is_model_audited,
)
from .constants import SYSTEM, USER
from .models import ActionLog, DiffLog
from .signals import (
    _configured_database_aliases,
    _startup_synced_database_aliases,
    build_create_triggers_sql,
    should_sync_pg_audit_triggers_on_start,
    sync_pg_audit_triggers_on_start,
)


def sample_extra_informations_getter(*, request=None, model=None):
    return {
        "has_request": request is not None,
        "has_model": model is not None,
    }


def sample_actor_role_getter(
    *, request=None, user=None, actor_type=None, source=None, **kwargs
):
    username = user.get_username() if user is not None else "anonymous"
    return f"{actor_type}:{source}:{username}"


class PGAuditModelsExtraInformationsTests(SimpleTestCase):
    def test_serialize_extra_informations_should_round_trip_json_data(self):
        serialized_value = serialize_extra_informations(
            {"study_id": 10, "site_id": "BR-001"}
        )

        self.assertEqual(
            deserialize_extra_informations(serialized_value),
            {"study_id": 10, "site_id": "BR-001"},
        )

    def test_merge_extra_informations_should_merge_dicts_with_override_precedence(self):
        self.assertEqual(
            merge_extra_informations(
                {"study_id": 10, "site_id": "BR-001"},
                {"site_id": "BR-002", "sponsor_id": 99},
            ),
            {"study_id": 10, "site_id": "BR-002", "sponsor_id": 99},
        )

    def test_call_with_supported_kwargs_should_ignore_unknown_arguments(self):
        self.assertEqual(
            call_with_supported_kwargs(
                sample_extra_informations_getter,
                {"request": object(), "model": None, "ignored": True},
            ),
            {"has_request": True, "has_model": False},
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "default_extra_informations_getter": sample_extra_informations_getter
        }
    )
    def test_get_pg_audit_config_should_merge_project_settings(self):
        self.assertIs(
            get_pg_audit_config()["default_extra_informations_getter"],
            sample_extra_informations_getter,
        )

    def test_project_pg_extra_informations_should_not_store_default_data(self):
        self.assertIsNone(
            get_pg_audit_extra_informations(
                request=FakeRequest(),
                model=Category,
                ref_id=10,
                source="core.category.update",
                url="/admin/login/",
            )
        )


class FakeCursor:
    def mogrify(self, sql, params):
        return ("'%s'" % str(params[0]).replace("'", "''")).encode("utf-8")


class FakeUser:
    is_authenticated = True
    groups = SimpleNamespace(
        exists=lambda: False,
        first=lambda: None,
    )

    def get_username(self):
        return "request-user"


class FakeRequest:
    META = {}
    POST = {}
    encoding = "utf-8"
    method = "PATCH"
    path = "/fake-path/"
    user = FakeUser()

    def __init__(self, body=b""):
        self.body = body

    def get_full_path(self):
        return "/fake-path/"


class PGAuditModelsContextTests(SimpleTestCase):
    def get_empty_pg_settings(self):
        from . import PG_SETTINGS

        return {setting_name: "" for setting_name in PG_SETTINGS}

    def test_audit_should_read_reason_for_change_from_json_body(self):
        request = FakeRequest(
            body=b'{"reason_for_change": {"name": "Name correction"}}'
        )

        with patch(
            "drf_audit_trail.pg_audit_models.get_current_pg_settings",
            return_value=self.get_empty_pg_settings(),
        ), patch("drf_audit_trail.pg_audit_models.set_pg_settings") as set_pg_settings:
            with audit(request=request):
                pass

        initial_settings = set_pg_settings.call_args_list[0].args[0]
        self.assertEqual(initial_settings[ACTOR_TYPE_SETTING], USER)
        self.assertEqual(
            deserialize_reason_for_change(initial_settings[REASON_FOR_CHANGE_SETTING]),
            {"name": "Name correction"},
        )

    def test_system_audit_should_mark_context_as_system(self):
        with patch(
            "drf_audit_trail.pg_audit_models.get_current_pg_settings",
            return_value=self.get_empty_pg_settings(),
        ), patch("drf_audit_trail.pg_audit_models.set_pg_settings") as set_pg_settings:
            with system_audit(
                source="emails.send_welcome",
                reason_for_change="Welcome email sent",
            ):
                pass

        initial_settings = set_pg_settings.call_args_list[0].args[0]
        self.assertEqual(initial_settings[SOURCE_SETTING], "emails.send_welcome")
        self.assertEqual(initial_settings[USER_SETTING], "system")
        self.assertEqual(initial_settings[ACTOR_TYPE_SETTING], SYSTEM)
        self.assertEqual(
            initial_settings[ACTOR_ROLE_SETTING],
            DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE,
        )
        self.assertEqual(
            initial_settings[REASON_FOR_CHANGE_SETTING],
            "Welcome email sent",
        )

    def test_reason_dict_should_include_model_column_names(self):
        self.assertEqual(
            normalize_reason_for_model_columns(
                {"content_type": "Permission app changed"},
                Permission,
            ),
            {
                "content_type": "Permission app changed",
                "content_type_id": "Permission app changed",
            },
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={"default_actor_role_getter": sample_actor_role_getter}
    )
    def test_audit_should_read_actor_role_from_default_getter_setting(self):
        request = FakeRequest()

        with patch(
            "drf_audit_trail.pg_audit_models.get_current_pg_settings",
            return_value=self.get_empty_pg_settings(),
        ), patch("drf_audit_trail.pg_audit_models.set_pg_settings") as set_pg_settings:
            with audit(request=request, source="tests.actor_role"):
                pass

        initial_settings = set_pg_settings.call_args_list[0].args[0]
        self.assertEqual(
            initial_settings[ACTOR_ROLE_SETTING],
            "User:tests.actor_role:request-user",
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={"default_actor_role_getter": sample_actor_role_getter}
    )
    def test_audit_should_prefer_explicit_actor_role_over_default_getter(self):
        request = FakeRequest()

        with patch(
            "drf_audit_trail.pg_audit_models.get_current_pg_settings",
            return_value=self.get_empty_pg_settings(),
        ), patch("drf_audit_trail.pg_audit_models.set_pg_settings") as set_pg_settings:
            with audit(
                request=request,
                source="tests.actor_role",
                actor_role="Site User",
            ):
                pass

        initial_settings = set_pg_settings.call_args_list[0].args[0]
        self.assertEqual(initial_settings[ACTOR_ROLE_SETTING], "Site User")

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={"default_actor_role_getter": sample_actor_role_getter}
    )
    def test_audit_callback_should_allow_actor_role_metadata(self):
        request = FakeRequest()

        def callback(*args, **kwargs):
            return {
                "model": Category,
                "actor_role": "Callback Role",
            }

        with patch(
            "drf_audit_trail.pg_audit_models.get_current_pg_settings",
            return_value=self.get_empty_pg_settings(),
        ), patch("drf_audit_trail.pg_audit_models.set_pg_settings") as set_pg_settings:

            @audit(request=request, callback=callback, source="tests.actor_role")
            def wrapped():
                return None

            wrapped()

        initial_settings = set_pg_settings.call_args_list[0].args[0]
        self.assertEqual(initial_settings[ACTOR_ROLE_SETTING], "Callback Role")


class PGAuditModelsVerboseNameTests(SimpleTestCase):
    def setUp(self):
        self.action_log = ActionLog(ref_name=Category._meta.db_table)
        self.diff_log = DiffLog(
            ref_name=Category._meta.db_table,
            column_name="name",
        )

    def test_models_should_expose_verbose_name_properties(self):
        self.assertEqual(self.action_log.model_verbose_name, "category")
        self.assertEqual(self.diff_log.model_verbose_name, "category")
        self.assertEqual(self.diff_log.field_verbose_name, "name")

    def test_admin_should_use_verbose_name_labels(self):
        action_log_admin = ActionLogAdmin(ActionLog, admin.site)

        self.assertEqual(action_log_admin.get_ref_name(self.action_log), "category")
        self.assertEqual(action_log_admin.get_ref_name.short_description, "model")


class PGAuditModelsConfigTests(SimpleTestCase):
    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={},
    )
    def test_empty_config_should_not_audit_models(self):
        self.assertEqual(get_audited_model_tables(), ())
        self.assertFalse(is_model_audited(Category))
        self.assertFalse(is_model_audited(User))

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "audit_all_models": True,
            "excluded_apps": [],
        }
    )
    def test_audit_all_models_should_exclude_pg_audit_models_by_default(self):
        audited_tables = get_audited_model_tables()

        self.assertIn("core_category", audited_tables)
        self.assertTrue(is_model_audited(Category))
        self.assertFalse(is_model_audited(ActionLog))
        self.assertNotIn("pg_audit_models_actionlog", audited_tables)

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category", "auth_user", Group),
        }
    )
    def test_models_should_accept_labels_db_tables_and_model_classes(self):
        audited_tables = get_audited_model_tables()

        self.assertEqual(audited_tables, ("auth_group", "auth_user", "core_category"))
        self.assertTrue(is_model_audited(Category))
        self.assertTrue(is_model_audited(User))
        self.assertTrue(is_model_audited(Group))
        self.assertFalse(is_model_audited(Product))

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("external_table",),
        }
    )
    def test_models_should_preserve_raw_table_names(self):
        self.assertEqual(get_audited_model_tables(), ("external_table",))

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "audit_all_models": True,
            "excluded_apps": ["core", "pg_audit_models"],
            "excluded_models": ["auth.User"],
        }
    )
    def test_excluded_apps_and_models_should_remove_audited_models(self):
        audited_tables = get_audited_model_tables()

        self.assertNotIn("core_category", audited_tables)
        self.assertNotIn("auth_user", audited_tables)
        self.assertFalse(is_model_audited(Category))
        self.assertFalse(is_model_audited(User))
        self.assertTrue(is_model_audited(Group))

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "api_views_modules": ["custom.audit_viewsets"],
            "api_views_module_suffixes": ["views", "api.viewsets"],
        }
    )
    def test_api_views_module_paths_should_include_explicit_and_app_suffixes(self):
        module_paths = get_api_views_module_paths()

        self.assertEqual(module_paths[0], "custom.audit_viewsets")
        self.assertIn("core.views", module_paths)
        self.assertIn("core.api.viewsets", module_paths)

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "django_views_modules": ["custom.django_views"],
            "django_views_module_suffixes": ["views", "web.views"],
        }
    )
    def test_django_views_module_paths_should_include_explicit_and_app_suffixes(self):
        module_paths = get_django_views_module_paths()

        self.assertEqual(module_paths[0], "custom.django_views")
        self.assertIn("core.views", module_paths)
        self.assertIn("core.web.views", module_paths)

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core_category",),
        }
    )
    def test_build_create_triggers_sql_should_use_public_schema_and_tables(self):
        sql = build_create_triggers_sql(
            FakeCursor(),
            get_audited_model_tables(),
        )

        self.assertIn("schemaname = 'public'", sql)
        self.assertIn("ARRAY['core_category']::TEXT[]", sql)
        self.assertIn("DROP TRIGGER IF EXISTS %I ON %I", sql)

    def test_dynamic_primary_key_migration_should_not_assume_id_column(self):
        migration = importlib.import_module(
            "drf_audit_trail.pg_audit_models.migrations.0002_create_trigger"
        )

        self.assertIn("v_ref_id TEXT", migration.CREATE_FUNCTION)
        self.assertIn("v_row_ref_id TEXT", migration.CREATE_FUNCTION)
        self.assertIn("TG_RELID", migration.CREATE_FUNCTION)
        self.assertIn("v_pk_column", migration.CREATE_FUNCTION)
        self.assertNotIn("OLD.id", migration.CREATE_FUNCTION)
        self.assertNotIn("NEW.id", migration.CREATE_FUNCTION)


class PGAuditModelsStartupSyncTests(SimpleTestCase):
    def test_startup_sync_should_skip_before_apps_are_ready(self):
        from . import signals

        with patch.object(signals.django_apps, "ready", False), patch.object(
            signals, "sync_pg_audit_triggers"
        ) as sync_pg_audit_triggers:
            status = signals.sync_pg_audit_triggers_on_start(argv=["gunicorn"])

        self.assertIsNone(status)
        sync_pg_audit_triggers.assert_not_called()

    def test_startup_sync_should_skip_migration_and_utility_commands(self):
        self.assertFalse(
            should_sync_pg_audit_triggers_on_start(["manage.py", "migrate"])
        )
        self.assertFalse(should_sync_pg_audit_triggers_on_start(["manage.py", "test"]))
        self.assertFalse(
            should_sync_pg_audit_triggers_on_start(
                ["manage.py", "sync_pg_audit_triggers"]
            )
        )

    def test_startup_sync_should_run_for_runtime_processes(self):
        self.assertTrue(
            should_sync_pg_audit_triggers_on_start(["manage.py", "runserver"])
        )
        self.assertTrue(should_sync_pg_audit_triggers_on_start(["gunicorn"]))

    def test_startup_sync_should_skip_when_schema_is_not_ready(self):
        from . import signals

        _startup_synced_database_aliases.clear()
        with patch.object(
            signals, "is_pg_audit_database_ready", return_value=False
        ), patch.object(signals, "sync_pg_audit_triggers") as sync_pg_audit_triggers:
            status = signals.sync_pg_audit_triggers_on_start(argv=["gunicorn"])

        self.assertIsNone(status)
        sync_pg_audit_triggers.assert_not_called()

    def test_request_started_signal_should_trigger_startup_sync(self):
        from . import signals

        with patch.object(signals, "sync_pg_audit_triggers_on_start") as sync:
            signals.run_pg_audit_startup_sync_on_request(sender=object())

        sync.assert_called_once_with()

    def test_connection_created_signal_should_trigger_startup_sync_for_alias(self):
        from . import signals

        connection_mock = SimpleNamespace(alias="default")

        with patch.object(signals, "sync_pg_audit_triggers_on_start") as sync:
            signals.run_pg_audit_startup_sync_on_connection(
                sender=object(),
                connection=connection_mock,
            )

        sync.assert_called_once_with(using="default")

    def test_post_migrate_hook_should_skip_when_schema_is_not_ready(self):
        from . import signals

        _configured_database_aliases.clear()
        with patch.object(
            signals, "is_pg_audit_database_ready", return_value=False
        ), patch.object(signals, "sync_pg_audit_triggers") as sync:
            signals.run_custom_post_migrate_hook(sender=object(), using="default")

        sync.assert_not_called()

    def test_post_migrate_hook_should_sync_when_schema_is_ready(self):
        from . import signals

        _configured_database_aliases.clear()
        with patch.object(
            signals, "is_pg_audit_database_ready", return_value=True
        ), patch.object(
            signals,
            "sync_pg_audit_triggers",
            return_value={"database_alias": "default"},
        ) as sync:
            signals.run_custom_post_migrate_hook(sender=object(), using="default")

        sync.assert_called_once_with(
            using="default",
            config=signals.get_pg_audit_config(),
        )


class PGAuditModelsActionLogAdminExportTests(TestCase):
    databases = {"default", "audit_trail"}

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin",
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.action_log = ActionLog.objects.create(
            source="tests.update_category",
            ref_name=Category._meta.db_table,
            ref_id="1",
            username="admin",
            actor_type=USER,
            url="/api/categories/1/",
        )
        DiffLog.objects.create(
            action_log=self.action_log,
            event_type="UPDATE",
            ref_name=Category._meta.db_table,
            ref_id="1",
            column_name="name",
            old_value="Old category",
            new_value="New category",
            reason_for_change="Name correction",
        )
        DiffLog.objects.create(
            action_log=self.action_log,
            event_type="UPDATE",
            ref_name=Category._meta.db_table,
            ref_id="1",
            column_name="description",
            old_value="Old description",
            new_value="New description",
            reason_for_change="Description correction",
        )
        self.system_action_log = ActionLog.objects.create(
            source="tests.system_task",
            ref_name=Category._meta.db_table,
            ref_id="2",
            username="system",
            actor_type=SYSTEM,
            url="/tasks/categories/sync/",
        )
        DiffLog.objects.create(
            action_log=self.system_action_log,
            event_type="UPDATE",
            ref_name=Category._meta.db_table,
            ref_id="2",
            column_name="name",
            old_value="Draft",
            new_value="Synced",
            reason_for_change="System sync",
        )

    def test_changelist_should_show_export_links(self):
        response = self.client.get(
            reverse("admin:pg_audit_models_actionlog_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Export CSV")
        self.assertContains(response, "Export XLS")
        self.assertContains(response, "Export PDF")

    def test_csv_export_should_use_action_log_field_resolvers(self):
        response = self.client.get(
            reverse("admin:pg_audit_models_actionlog_export", args=["csv"])
            + "?source__exact=tests.update_category"
        )

        content = response.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="pg_action_log_report.csv"',
        )
        self.assertIn("source__exact=tests.update_category", content)
        self.assertIn("Username", content)
        self.assertIn("Action Source", content)
        self.assertIn("URL", content)
        self.assertIn("admin", content)
        self.assertIn("UPDATE", content)
        self.assertIn("tests.update_category", content)
        self.assertIn("category:1", content)
        self.assertIn("name", content)
        self.assertIn("Old category", content)
        self.assertIn("New category", content)
        self.assertIn("Description correction", content)
        self.assertNotIn("tests.system_task", content)

    def test_xls_export_should_reuse_audit_report_template(self):
        response = self.client.get(
            reverse("admin:pg_audit_models_actionlog_export", args=["xls"])
            + "?source__exact=tests.update_category"
        )

        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.ms-excel; charset=utf-8",
        )
        self.assertIn("Who Pulled the report", content)
        self.assertIn("Action Source", content)
        self.assertIn("tests.update_category", content)
        self.assertIn("Old category", content)
        self.assertIn("New description", content)
        self.assertNotIn("tests.system_task", content)

    @patch("drf_audit_trail.report_export.HTML")
    def test_pdf_export_should_reuse_audit_report_template(self, html_mock):
        html_mock.return_value.write_pdf.return_value = b"%PDF-1.4"

        response = self.client.get(
            reverse("admin:pg_audit_models_actionlog_export", args=["pdf"])
            + "?source__exact=tests.update_category"
        )
        html_string = html_mock.call_args.kwargs["string"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, b"%PDF-1.4")
        self.assertIn("Who Pulled the report", html_string)
        self.assertIn("Action Source", html_string)
        self.assertIn("tests.update_category", html_string)
        self.assertIn("Old category", html_string)
        self.assertIn("New description", html_string)
        self.assertNotIn("tests.system_task", html_string)


class PGAuditModelsPatcherTests(SimpleTestCase):
    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "api_views_actions": ["create"],
        }
    )
    def test_patch_viewsets_should_respect_configured_api_view_actions(self):
        from . import patcher

        class CategoryViewSetForTest(ModelViewSet):
            queryset = Category.objects.none()

        with patch.object(
            patcher, "get_all_viewsets", return_value=[CategoryViewSetForTest]
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_viewsets()

        decorate_method.assert_called_once_with(
            CategoryViewSetForTest,
            "create",
            patcher.get_model_viewset_callback,
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "api_views_actions": ["create"],
        }
    )
    def test_patch_viewsets_should_patch_drf_mixin_viewsets(self):
        from . import patcher

        class CategoryCreateViewSetForTest(CreateModelMixin, GenericViewSet):
            queryset = Category.objects.none()

        with patch.object(
            patcher, "get_all_viewsets", return_value=[CategoryCreateViewSetForTest]
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_viewsets()

        decorate_method.assert_called_once_with(
            CategoryCreateViewSetForTest,
            "create",
            patcher.get_model_viewset_callback,
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "api_views_actions": ["create"],
        }
    )
    def test_patch_viewsets_should_patch_plain_viewsets_with_audit_model(self):
        from . import patcher

        class CategoryPlainViewSetForTest(ViewSet):
            audit_model = Category

            def create(self, request, *args, **kwargs):
                return None

        with patch.object(
            patcher, "get_all_viewsets", return_value=[CategoryPlainViewSetForTest]
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_viewsets()

        decorate_method.assert_called_once_with(
            CategoryPlainViewSetForTest,
            "create",
            patcher.get_model_viewset_callback,
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "api_views_actions": ["create"],
        }
    )
    def test_patch_viewsets_should_always_patch_custom_actions(self):
        from . import patcher

        class CategoryViewSetWithActionForTest(ModelViewSet):
            queryset = Category.objects.none()

            @action(methods=["post"], detail=True)
            def publish(self, request, pk=None):
                return None

        with patch.object(
            patcher, "get_all_viewsets", return_value=[CategoryViewSetWithActionForTest]
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_viewsets()

        decorate_method.assert_has_calls(
            [
                call(
                    CategoryViewSetWithActionForTest,
                    "create",
                    patcher.get_model_viewset_callback,
                ),
                call(
                    CategoryViewSetWithActionForTest,
                    "publish",
                    patcher.get_model_viewset_callback,
                ),
            ],
            any_order=True,
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "api_views_actions": ["create"],
        }
    )
    def test_patch_viewsets_should_skip_non_audited_model_viewsets(self):
        from . import patcher

        class ProductViewSetForTest(ModelViewSet):
            queryset = Product.objects.none()

        with patch.object(
            patcher, "get_all_viewsets", return_value=[ProductViewSetForTest]
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_viewsets()

        decorate_method.assert_not_called()

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "api_views_methods": ["post"],
        }
    )
    def test_patch_api_views_should_patch_direct_api_views_with_audit_model(self):
        from . import patcher

        class CategoryAPIViewForTest(APIView):
            audit_model = Category

            def post(self, request, *args, **kwargs):
                return None

        with patch.object(
            patcher, "get_all_api_views", return_value=[CategoryAPIViewForTest]
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_api_views()

        decorate_method.assert_called_once_with(
            CategoryAPIViewForTest,
            "post",
            patcher.get_api_view_callback,
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "api_views_methods": ["get", "post"],
        }
    )
    def test_patch_api_views_should_patch_drf_generic_api_views(self):
        from . import patcher

        class CategoryListCreateAPIViewForTest(ListCreateAPIView):
            queryset = Category.objects.none()

        with patch.object(
            patcher,
            "get_all_api_views",
            return_value=[CategoryListCreateAPIViewForTest],
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_api_views()

        decorate_method.assert_has_calls(
            [
                call(
                    CategoryListCreateAPIViewForTest,
                    "get",
                    patcher.get_api_view_callback,
                ),
                call(
                    CategoryListCreateAPIViewForTest,
                    "post",
                    patcher.get_api_view_callback,
                ),
            ],
            any_order=True,
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "api_views_methods": ["post"],
        }
    )
    def test_patch_api_views_should_skip_non_audited_models(self):
        from . import patcher

        class ProductAPIViewForTest(APIView):
            audit_model = Product

            def post(self, request, *args, **kwargs):
                return None

        with patch.object(
            patcher, "get_all_api_views", return_value=[ProductAPIViewForTest]
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_api_views()

        decorate_method.assert_not_called()

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "api_views_methods": ["post"],
        }
    )
    def test_patch_api_views_should_not_patch_viewsets_twice(self):
        from . import patcher

        class CategoryViewSetForApiSkipTest(ModelViewSet):
            queryset = Category.objects.none()

        with patch.object(
            patcher,
            "get_all_api_views",
            return_value=[CategoryViewSetForApiSkipTest],
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_api_views()

        decorate_method.assert_not_called()

    def test_api_view_callback_should_support_wrapped_drf_request_url(self):
        from . import patcher

        class CategoryAPIViewForCallbackTest(APIView):
            audit_model = Category

        class DjangoRequest:
            def get_full_path(self):
                return "/api/categories/1/"

        request = SimpleNamespace(_request=DjangoRequest())

        metadata = patcher.get_api_view_callback(
            CategoryAPIViewForCallbackTest,
            request,
            pk=1,
        )

        self.assertEqual(metadata["model"], Category)
        self.assertEqual(metadata["pk"], 1)
        self.assertEqual(metadata["request"], request)
        self.assertEqual(metadata["url"], "/api/categories/1/")

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "django_views_methods": ["post"],
        }
    )
    def test_patch_django_views_should_patch_django_class_based_views(self):
        from . import patcher

        class CategoryDjangoViewForTest(View):
            model = Category

            def post(self, request, *args, **kwargs):
                return None

        with patch.object(
            patcher, "get_all_django_views", return_value=[CategoryDjangoViewForTest]
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_django_views()

        decorate_method.assert_called_once_with(
            CategoryDjangoViewForTest,
            "post",
            patcher.get_django_view_callback,
        )

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "models": ("core.Category",),
            "django_views_methods": ["post"],
        }
    )
    def test_patch_django_views_should_skip_drf_api_views(self):
        from . import patcher

        class CategoryAPIViewForDjangoSkipTest(APIView):
            audit_model = Category

            def post(self, request, *args, **kwargs):
                return None

        with patch.object(
            patcher,
            "get_all_django_views",
            return_value=[CategoryAPIViewForDjangoSkipTest],
        ), patch.object(patcher, "decorate_method") as decorate_method:
            patcher.patch_django_views()

        decorate_method.assert_not_called()

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "api_views_modules": ["custom.views"],
            "api_views_module_suffixes": [],
        }
    )
    def test_import_api_views_modules_should_import_package_children(self):
        from . import patcher

        imported_modules = []
        package = SimpleNamespace(__name__="custom.views", __path__=["/tmp/views"])

        def fake_import_module(module_path):
            imported_modules.append(module_path)
            return package if module_path == "custom.views" else SimpleNamespace()

        with patch.object(
            patcher, "import_module", side_effect=fake_import_module
        ), patch.object(
            patcher.pkgutil,
            "walk_packages",
            return_value=[SimpleNamespace(name="custom.views.products")],
        ):
            patcher.import_api_views_modules()

        self.assertEqual(imported_modules, ["custom.views", "custom.views.products"])

    @override_settings(
        DRF_AUDIT_TRAIL_PG_AUDIT={
            "django_views_modules": ["custom.django_views"],
            "django_views_module_suffixes": [],
        }
    )
    def test_import_django_views_modules_should_import_package_children(self):
        from . import patcher

        imported_modules = []
        package = SimpleNamespace(
            __name__="custom.django_views",
            __path__=["/tmp/django_views"],
        )

        def fake_import_module(module_path):
            imported_modules.append(module_path)
            return (
                package if module_path == "custom.django_views" else SimpleNamespace()
            )

        with patch.object(
            patcher, "import_module", side_effect=fake_import_module
        ), patch.object(
            patcher.pkgutil,
            "walk_packages",
            return_value=[SimpleNamespace(name="custom.django_views.products")],
        ):
            patcher.import_django_views_modules()

        self.assertEqual(
            imported_modules,
            ["custom.django_views", "custom.django_views.products"],
        )


@skipUnless(connection.vendor == "postgresql", "PostgreSQL trigger tests only")
class PGAuditModelsPostgreSQLTriggerTests(TransactionTestCase):
    uuid_table_name = "pg_audit_uuid_target"
    stale_table_name = "pg_audit_stale_target"

    def setUp(self):
        migration = importlib.import_module(
            "drf_audit_trail.pg_audit_models.migrations.0002_create_trigger"
        )
        with connection.cursor() as cursor:
            cursor.execute(migration.CREATE_FUNCTION)
            self.drop_table(cursor, self.uuid_table_name)
            self.drop_table(cursor, self.stale_table_name)

        ActionLog.objects.filter(
            ref_name__in=[self.uuid_table_name, self.stale_table_name]
        ).delete()

    def tearDown(self):
        _startup_synced_database_aliases.clear()
        with connection.cursor() as cursor:
            self.drop_table(cursor, self.uuid_table_name)
            self.drop_table(cursor, self.stale_table_name)

        ActionLog.objects.filter(
            ref_name__in=[self.uuid_table_name, self.stale_table_name]
        ).delete()

    def drop_table(self, cursor, table_name):
        cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    def create_uuid_table(self, row_id):
        with connection.cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE {self.uuid_table_name} (
                    uuid_key UUID PRIMARY KEY,
                    name TEXT,
                    status TEXT
                )
                """)
            cursor.execute(
                f"""
                INSERT INTO {self.uuid_table_name} (uuid_key, name, status)
                VALUES (%s, %s, %s)
                """,
                [str(row_id), "Original", "draft"],
            )
            cursor.execute(build_create_triggers_sql(cursor, (self.uuid_table_name,)))

    def create_uuid_table_without_trigger(self, row_id):
        with connection.cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE {self.uuid_table_name} (
                    uuid_key UUID PRIMARY KEY,
                    name TEXT,
                    status TEXT
                )
                """)
            cursor.execute(
                f"""
                INSERT INTO {self.uuid_table_name} (uuid_key, name, status)
                VALUES (%s, %s, %s)
                """,
                [str(row_id), "Original", "draft"],
            )

    def trigger_exists(self, cursor, table_name):
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.triggers
                WHERE trigger_schema = 'public'
                  AND event_object_schema = 'public'
                  AND event_object_table = %s
                  AND trigger_name = %s
            )
            """,
            [table_name, f"trg_log_update_{table_name}"],
        )
        return cursor.fetchone()[0]

    def test_trigger_should_store_uuid_primary_key_reason_and_extra_informations(self):
        row_id = uuid.uuid4()
        self.create_uuid_table(row_id)

        with system_audit(
            source="tests.uuid_update",
            reason_for_change={"name": "Name correction"},
            extra_informations={"study_id": 10},
        ):
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {self.uuid_table_name} SET name = %s WHERE uuid_key = %s",
                    ["Changed", str(row_id)],
                )

        action_log = ActionLog.objects.get(
            source="tests.uuid_update",
            ref_name=self.uuid_table_name,
        )
        diff_log = DiffLog.objects.get(action_log=action_log, column_name="name")

        self.assertEqual(action_log.ref_id, str(row_id))
        self.assertEqual(action_log.extra_informations, {"study_id": 10})
        self.assertEqual(diff_log.ref_id, str(row_id))
        self.assertEqual(diff_log.event_type, "UPDATE")
        self.assertEqual(diff_log.old_value, "Original")
        self.assertEqual(diff_log.new_value, "Changed")
        self.assertEqual(diff_log.reason_for_change, "Name correction")

    def test_trigger_logs_should_rollback_with_transaction(self):
        row_id = uuid.uuid4()
        self.create_uuid_table(row_id)

        try:
            with transaction.atomic():
                with system_audit(source="tests.rollback"):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"""
                            UPDATE {self.uuid_table_name}
                            SET name = %s
                            WHERE uuid_key = %s
                            """,
                            ["Rolled back", str(row_id)],
                        )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass

        self.assertFalse(
            ActionLog.objects.filter(
                source="tests.rollback",
                ref_name=self.uuid_table_name,
            ).exists()
        )

    def test_trigger_reconcile_should_drop_stale_managed_triggers(self):
        with connection.cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE {self.stale_table_name} (
                    id INTEGER PRIMARY KEY,
                    name TEXT
                )
                """)
            cursor.execute(build_create_triggers_sql(cursor, (self.stale_table_name,)))
            self.assertTrue(self.trigger_exists(cursor, self.stale_table_name))

            cursor.execute(build_create_triggers_sql(cursor, ()))
            self.assertFalse(self.trigger_exists(cursor, self.stale_table_name))

    def test_sync_command_should_create_triggers_for_current_settings(self):
        row_id = uuid.uuid4()
        self.create_uuid_table_without_trigger(row_id)

        with connection.cursor() as cursor:
            self.assertFalse(self.trigger_exists(cursor, self.uuid_table_name))

        with override_settings(
            DRF_AUDIT_TRAIL_PG_AUDIT={"models": (self.uuid_table_name,)}
        ):
            output = StringIO()
            call_command("sync_pg_audit_triggers", stdout=output)

        with connection.cursor() as cursor:
            self.assertTrue(self.trigger_exists(cursor, self.uuid_table_name))

        command_output = output.getvalue()
        self.assertIn(self.uuid_table_name, command_output)
        self.assertIn("Missing triggers: none", command_output)

    def test_sync_command_check_should_report_missing_triggers(self):
        row_id = uuid.uuid4()
        self.create_uuid_table_without_trigger(row_id)

        with override_settings(
            DRF_AUDIT_TRAIL_PG_AUDIT={"models": (self.uuid_table_name,)}
        ):
            output = StringIO()
            with self.assertRaises(CommandError) as context:
                call_command("sync_pg_audit_triggers", "--check", stdout=output)

        self.assertIn(self.uuid_table_name, str(context.exception))
        self.assertIn("Missing triggers:", output.getvalue())

    def test_startup_sync_should_create_triggers_when_schema_is_ready(self):
        row_id = uuid.uuid4()
        self.create_uuid_table_without_trigger(row_id)
        _startup_synced_database_aliases.clear()

        with connection.cursor() as cursor:
            self.assertFalse(self.trigger_exists(cursor, self.uuid_table_name))

        with override_settings(
            DRF_AUDIT_TRAIL_PG_AUDIT={"models": (self.uuid_table_name,)}
        ):
            status = sync_pg_audit_triggers_on_start(argv=["gunicorn"])

        with connection.cursor() as cursor:
            self.assertTrue(self.trigger_exists(cursor, self.uuid_table_name))

        self.assertIsNotNone(status)
        self.assertIn(self.uuid_table_name, status["audited_tables"])
        self.assertNotIn(self.uuid_table_name, status["missing_tables"])

    def test_startup_sync_should_run_once_per_process(self):
        row_id = uuid.uuid4()
        self.create_uuid_table_without_trigger(row_id)
        _startup_synced_database_aliases.clear()

        with override_settings(
            DRF_AUDIT_TRAIL_PG_AUDIT={"models": (self.uuid_table_name,)}
        ):
            self.assertIsNotNone(sync_pg_audit_triggers_on_start(argv=["gunicorn"]))
            self.assertIsNone(sync_pg_audit_triggers_on_start(argv=["gunicorn"]))
