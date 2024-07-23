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

    request = models.ForeignKey(
        RequestAuditEvent,
        on_delete=models.CASCADE,
        verbose_name=_("Request"),
        null=True,
    )

    def register_step(self, **kwargs):
        pass

    def __str__(self) -> str:
        return "ProcessAuditEvent: %s" % self.pk

    class Meta:
        verbose_name = _("Process audit event")
        verbose_name_plural = _("Process audit events")
        db_table = "process_audit_event"
