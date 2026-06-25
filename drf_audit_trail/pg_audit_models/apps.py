from django.apps import AppConfig, apps
from django.db.models import ForeignKey

APP_NAME = "pg_audit_models"


class PgAuditModelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = f"drf_audit_trail.{APP_NAME}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_table_mapping = {}
        self.related_model_table_mapping = {}
        self.field_verbose_name_mapping = {}
        self.model_verbose_name_mapping = {}

    def ready(self):
        from . import patcher, signals

        patcher.patch_admin()
        patcher.patch_viewsets()
        patcher.patch_api_views()
        patcher.patch_django_views()

        if not self.model_table_mapping:
            for model in apps.get_models():
                self.model_verbose_name_mapping[model._meta.db_table] = str(
                    model._meta.verbose_name
                )
                self.model_table_mapping[model._meta.db_table] = model
                for field in model._meta.get_fields():
                    if hasattr(field, "column"):
                        key = f"{field.model._meta.db_table}.{field.column}"
                        if isinstance(field, ForeignKey):
                            self.related_model_table_mapping[key] = field.related_model
                        self.field_verbose_name_mapping[key] = str(field.verbose_name)

    def get_object_by_db_table(self, db_table, pk):
        if db_table and pk:
            return self.model_table_mapping[db_table].objects.filter(pk=pk).first()
        return None

    def get_related_object_by_db_table(self, db_table, column_name, pk):
        key = f"{db_table}.{column_name}"
        if key in self.related_model_table_mapping and pk:
            return self.related_model_table_mapping[key].objects.filter(pk=pk).first()
        return None

    def get_field_verbose_name_by_db_table(self, db_table, column_name):
        key = f"{db_table}.{column_name}"
        return self.field_verbose_name_mapping.get(key, column_name)

    def get_model_verbose_name_by_db_table(self, db_table):
        return self.model_verbose_name_mapping.get(db_table, db_table)
