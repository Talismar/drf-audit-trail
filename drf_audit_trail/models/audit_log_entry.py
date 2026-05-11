from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from drf_audit_trail.mixins import BaseModelMixin
from drf_audit_trail.utils import deserialize_audit_value

from .request_audit_event import RequestAuditEvent


class AuditLogEntry(BaseModelMixin):
    USER = "User"
    SYSTEM = "System"
    ACTOR_TYPES = (
        (USER, _("User")),
        (SYSTEM, _("System")),
    )

    request = models.ForeignKey(
        RequestAuditEvent,
        on_delete=models.PROTECT,
        verbose_name=_("Request"),
        null=True,
        blank=True,
        related_name="audit_log_entries",
    )

    actor_identifier = models.CharField(
        _("Actor identifier"), null=True, blank=True, max_length=120, db_index=True
    )
    actor_role = models.CharField(
        _("Actor role"), null=True, blank=True, max_length=120
    )
    actor_type = models.CharField(
        _("Actor type"), choices=ACTOR_TYPES, max_length=20, default=USER
    )

    event_type = models.CharField(_("Event type"), max_length=64, db_index=True)
    action_description = models.TextField(_("Action description"))

    content_type = models.CharField(
        _("Content type"), max_length=255, null=True, blank=True, db_index=True
    )
    object_id = models.CharField(
        _("Object id"), max_length=255, null=True, blank=True, db_index=True
    )
    object_repr = models.TextField(_("Object representation"), null=True, blank=True)

    field_name = models.CharField(
        _("Field name"), max_length=255, null=True, blank=True
    )
    old_values = models.TextField(_("Old values"), null=True, blank=True)
    new_values = models.TextField(_("New values"), null=True, blank=True)
    reason_for_change = models.TextField(_("Reason for change"), null=True, blank=True)

    def clean(self):
        super().clean()
        if (
            self._has_value(self.old_values) or self._has_value(self.new_values)
        ) and not self._has_value(self.field_name):
            raise ValidationError(
                {
                    "field_name": _(
                        "Field name is required when old values or new values are set."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    @staticmethod
    def _has_value(value):
        return value is not None and str(value).strip() != ""

    def set_content_object(self, obj):
        self.content_type = f"{obj._meta.app_label}.{obj._meta.model_name}"
        self.object_id = str(obj.pk)
        self.object_repr = str(obj)

    def get_content_object(self):
        if not self.content_type or not self.object_id:
            return None

        try:
            app_label, model_name = self.content_type.split(".", 1)
            model = apps.get_model(app_label, model_name)
        except (LookupError, ValueError):
            return None

        try:
            return model._default_manager.get(pk=self.object_id)
        except (model.DoesNotExist, ValueError, TypeError):
            return None

    @property
    def old_values_data(self):
        return deserialize_audit_value(self.old_values)

    @property
    def new_values_data(self):
        return deserialize_audit_value(self.new_values)

    def __str__(self) -> str:
        return "AuditLogEntry: %s" % self.pk

    class Meta:
        verbose_name = _("Audit log entry")
        verbose_name_plural = _("Audit log entries")
