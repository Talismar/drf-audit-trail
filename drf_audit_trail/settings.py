from django.conf import settings
from django.db.utils import DEFAULT_DB_ALIAS

# Retention Period
"""
Refere-se a quanitade de tempo de armazenamento dos registros em dias
"""
DRF_AUDIT_TRAIL_RETENTION_PERIOD = getattr(
    settings, "DRF_AUDIT_TRAIL_RETENTION_PERIOD", 120
)

DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS = [r"^/api/.*?/"]
DRF_AUDIT_TRAIL_AUTH_URL = "/api/token/"
DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FALIED = getattr(
    settings, "DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FALIED", 401
)
DRF_AUDIT_TRAIL_DISABLE_ERROR_TRACETRACK = getattr(
    settings, "DRF_AUDIT_TRAIL_DISABLE_ERROR_TRACETRACK", False
)
DRF_AUDIT_TRAIL_DB_ALIAS = getattr(
    settings, "DRF_AUDIT_TRAIL_DB_ALIAS", DEFAULT_DB_ALIAS
)
