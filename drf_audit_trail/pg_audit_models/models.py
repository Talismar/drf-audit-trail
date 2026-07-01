from django.apps import apps
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from drf_audit_trail.mixins import ProtectedModelMixin

from .apps import APP_NAME
from .constants import ACTOR_TYPES, USER


class ActionLog(ProtectedModelMixin, models.Model):
    ACTOR_TYPES = ACTOR_TYPES

    source = models.CharField(max_length=255, null=True, db_index=True)
    ref_name = models.CharField(max_length=255, null=True, db_index=True)
    ref_id = models.CharField(max_length=255, null=True, db_index=True)
    executed_at = models.DateTimeField(auto_now_add=True, auto_created=True)
    username = models.CharField(max_length=255, null=True, db_index=True)
    actor_role = models.CharField(max_length=255, null=True)
    actor_type = models.CharField(
        choices=ACTOR_TYPES,
        max_length=20,
        default=USER,
    )
    url = models.CharField(max_length=255, null=True)
    extra_informations = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Extra information",
    )

    class Meta:
        verbose_name = "Log"
        verbose_name_plural = "Logs"
        indexes = [
            GinIndex(fields=["extra_informations"], name="pg_audit_extra_info_gin"),
        ]

    def __str__(self):
        return f"{self.id}"

    def get_ref(self):
        return apps.get_app_config(APP_NAME).get_object_by_db_table(
            self.ref_name, self.ref_id
        )

    def get_model_name(self):
        return apps.get_app_config(APP_NAME).get_model_verbose_name_by_db_table(
            self.ref_name
        )

    @property
    def model_verbose_name(self):
        return self.get_model_name()


class DiffLog(ProtectedModelMixin, models.Model):
    action_log = models.ForeignKey(ActionLog, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=25, db_index=True)
    ref_name = models.CharField(max_length=255, db_index=True)
    ref_id = models.CharField(max_length=255, null=True, db_index=True)
    column_name = models.CharField(max_length=255, db_index=True)
    old_value = models.TextField(null=True)
    new_value = models.TextField(null=True)
    reason_for_change = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.id}"

    def get_ref(self):
        return apps.get_app_config(APP_NAME).get_object_by_db_table(
            self.ref_name, self.ref_id
        )

    def get_old_value(self):
        if self.old_value and self.column_name.endswith("_id"):
            return (
                apps.get_app_config(APP_NAME).get_related_object_by_db_table(
                    self.ref_name, self.column_name, self.old_value
                )
                or self.old_value
            )
        return self.old_value

    def get_new_value(self):
        if self.new_value and self.column_name.endswith("_id"):
            return (
                apps.get_app_config(APP_NAME).get_related_object_by_db_table(
                    self.ref_name, self.column_name, self.new_value
                )
                or self.new_value
            )
        return self.new_value

    def get_field_name(self):
        return apps.get_app_config(APP_NAME).get_field_verbose_name_by_db_table(
            self.ref_name, self.column_name
        )

    def get_model_name(self):
        return apps.get_app_config(APP_NAME).get_model_verbose_name_by_db_table(
            self.ref_name
        )

    @property
    def action_description(self):
        if self.event_type == "UPDATE":
            return f"Updated ({self.field_verbose_name})"
        if self.event_type == "INSERT":
            return f"Created new ({self.model_verbose_name})"
        return f"Deleted ({self.model_verbose_name})"

    @property
    def field_verbose_name(self):
        return self.get_field_name()

    @property
    def model_verbose_name(self):
        return self.get_model_name()
