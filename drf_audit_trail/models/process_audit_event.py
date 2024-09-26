from django.db import models
from django.utils.translation import gettext_lazy as _

from drf_audit_trail.mixins import BaseModelMixin

from .request_audit_event import RequestAuditEvent


class ProcessAuditEvent(BaseModelMixin):
    """
    This is the model for the process audit trail.
    """

    name = models.CharField(_("Name"), max_length=255)
    description = models.TextField(_("Description"), null=True, blank=True)
    created_by = models.CharField(
        _("User identifier"), null=True, blank=True, max_length=120
    )

    request = models.ForeignKey(
        RequestAuditEvent,
        on_delete=models.CASCADE,
        verbose_name=_("Request"),
        null=True,
        blank=True,
        related_name="processes",
    )

    def register_step(self, **kwargs):
        pass

    def __str__(self) -> str:
        return "ProcessAuditEvent: %s" % self.pk

    class Meta:
        verbose_name = _("Process audit event")
        verbose_name_plural = _("Process audit events")


class StepAuditEvent(BaseModelMixin):
    process = models.ForeignKey(
        ProcessAuditEvent, on_delete=models.CASCADE, related_name="steps"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(_("Description"), null=True, blank=True)
    order = models.IntegerField()
    total_registrations = models.IntegerField(default=1)
    created_by = models.CharField(
        _("User identifier"), null=True, blank=True, max_length=120
    )

    def __str__(self) -> str:
        return "StepAuditEvent: %s" % self.pk

    class Meta:
        verbose_name = _("Step audit event")
        verbose_name_plural = _("Step audit events")


class RegistrationAuditEvent(BaseModelMixin):
    step = models.ForeignKey(
        StepAuditEvent, on_delete=models.CASCADE, related_name="registrations"
    )
    success = models.BooleanField()
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_by = models.CharField(
        _("User identifier"), null=True, blank=True, max_length=120
    )

    def __str__(self) -> str:
        return "RegistrationAuditEvent: %s" % self.pk

    class Meta:
        verbose_name = _("Registration audit event")
        verbose_name_plural = _("Registration audit events")
