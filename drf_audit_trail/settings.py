from django.conf import settings

# Retention Period
"""
Refere-se a quanitade de tempo de armazenamento dos registros em dias
"""
DRF_AUDIT_TRAIL_RETENTION_PERIOD = getattr(
    settings, "DRF_AUDIT_TRAIL_RETENTION_PERIOD", 120
)

DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS = getattr(
    settings, "DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS", [r"^/api/.*?/"]
)
DRF_AUDIT_TRAIL_AUTH_URL = getattr(settings, "DRF_AUDIT_TRAIL_AUTH_URL", "/api/token/")
DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FALIED = getattr(
    settings, "DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FALIED", 401
)

DRF_AUDIT_TRAIL_DATABASE_ALIAS = getattr(
    settings, "DRF_AUDIT_TRAIL_DATABASE_ALIAS", "audit_trail"
)
DRF_AUDIT_TRAIL_USER_PK_NAME = getattr(settings, "DRF_AUDIT_TRAIL_USER_PK_NAME", "pk")
DJANO_DEFAULT_DATABASE_ALIAS = getattr(
    settings, "DJANGO_DEFAULT_DATABASE_ALIAS", "default"
)
DRF_AUDIT_TRAIL_NOTSAVE_REQUEST_BODY_URLS = getattr(settings, "DRF_AUDIT_TRAIL_NOTSAVE_REQUEST_BODY_URLS", [])
DRF_AUDIT_TRAIL_NOTSAVE_RESPONSE_BODY_URLS = getattr(settings, "DRF_AUDIT_TRAIL_NOTSAVE_RESPONSE_BODY_URLS", [])