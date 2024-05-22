from django.db import models
from django.utils.translation import gettext_lazy as _

from drf_audit_trail.mixins import BaseModelMixin

from .request_audit_event import RequestAuditEvent


class LoginAuditEvent(BaseModelMixin):
    """
    This is the model for the login audit trail.
    """

    SIGNIN = "Sign in"
    SIGNOUT = "Sign out"
    FAILED = "Failed"
    STATUS = (
        (SIGNIN, _("Sign in")),
        (SIGNOUT, _("Sign out")),
        (FAILED, _("Failed")),
    )

    status = models.CharField(_("Status"), choices=STATUS, max_length=8)
    request = models.OneToOneField(RequestAuditEvent, on_delete=models.CASCADE)

    class Meta:
        verbose_name = _("Login audit event")
        verbose_name_plural = _("Login audit events")
        db_table = "login_audit_event"
