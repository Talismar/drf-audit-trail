from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DrfAuditTrailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "drf_audit_trail"
    verbose_name = _("DRF Audit Trail")
