from django.contrib.auth.signals import user_logged_out
from django.db import models
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from drf_audit_trail.managers import LoginAuditEventManager
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

    objects: LoginAuditEventManager = LoginAuditEventManager()

    class Meta:
        verbose_name = _("Login audit event")
        verbose_name_plural = _("Login audit events")


@receiver(user_logged_out)
def audit_user_logout(sender, request, user, **kwargs):
    drf_login_audit_event = request.META.get("drf_login_audit_event")
    drf_request_audit_event = request.META.get("drf_request_audit_event")

    if drf_login_audit_event is not None:
        drf_login_audit_event["status"] = LoginAuditEvent.SIGNOUT
    if drf_request_audit_event is not None:
        drf_request_audit_event["user"] = user
