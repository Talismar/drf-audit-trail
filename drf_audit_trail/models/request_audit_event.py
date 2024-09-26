from django.db import models
from django.utils.translation import gettext_lazy as _

from drf_audit_trail.managers import RequestAuditEventManager
from drf_audit_trail.mixins import BaseModelMixin


class RequestAuditEvent(BaseModelMixin):
    """
    This is the model for the request audit trail.
    """

    user = models.CharField(_("User identifier"), null=True, blank=True, max_length=120)

    ip_addresses = models.CharField(_("Ip addresses"), max_length=50, null=True)

    """
        methods: GET, POST, PUT, DELETE, PATCH, OPTIONS
    """
    method = models.CharField(_("Method"), max_length=10)
    url = models.CharField(_("URL"), null=False, max_length=2048)

    # Request Parameters
    query_params = models.CharField(
        _("Query Parameters"), blank=True, null=True, max_length=2048
    )
    request_type = models.CharField(
        _("Request Type"), max_length=10, null=True, blank=True
    )
    # body = models.TextField(_("Body"), blank=True, default=dict)

    # Response Information
    status_code = models.IntegerField(_("Status Code"), null=True)
    response_time = models.FloatField(_("Response Time (ms)"), null=True)
    response_size = models.IntegerField(_("Response Size (bytes)"), null=True)

    # Error Handling
    error_type = models.CharField(
        _("Error Type"), max_length=255, blank=True, null=True
    )
    error_message = models.TextField(_("Error Message"), blank=True, null=True)
    error_stacktrace = models.TextField(_("Error Stacktrace"), blank=True, null=True)

    objects: RequestAuditEventManager = RequestAuditEventManager()

    def __str__(self) -> str:
        return "RequestAuditEvent: %s" % self.pk

    class Meta:
        verbose_name = _("Request event")
        verbose_name_plural = _("Request events")
