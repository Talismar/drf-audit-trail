from django.conf import settings

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
DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE = getattr(
    settings, "DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_ROLE", "System"
)
DJANGO_DEFAULT_DATABASE_ALIAS = getattr(
    settings, "DJANGO_DEFAULT_DATABASE_ALIAS", "default"
)
DRF_AUDIT_TRAIL_NOTSAVE_REQUEST_BODY_URLS = getattr(
    settings, "DRF_AUDIT_TRAIL_NOTSAVE_REQUEST_BODY_URLS", []
)
DRF_AUDIT_TRAIL_NOTSAVE_RESPONSE_BODY_URLS = getattr(
    settings, "DRF_AUDIT_TRAIL_NOTSAVE_RESPONSE_BODY_URLS", []
)
DEFAULT_DRF_AUDIT_TRAIL_PG_AUDIT = {
    "audit_all_models": False,
    "models": None,
    "excluded_models": [],
    "api_views_modules": [],
    "api_views_module_suffixes": ["views", "api.views"],
    "api_views_actions": [
        "list",
        "create",
        "retrieve",
        "update",
        "partial_update",
        "destroy",
    ],
    "api_views_methods": ["get", "post", "put", "patch", "delete"],
    "django_views_modules": [],
    "django_views_module_suffixes": ["views"],
    "django_views_methods": ["get", "post", "put", "patch", "delete"],
    "reason_for_change_key": "reason_for_change",
    "default_extra_informations_getter": None,
    "default_actor_role_getter": "drf_audit_trail.utils.get_global_audit_actor_role",
}
DRF_AUDIT_TRAIL_PG_AUDIT = getattr(
    settings,
    "DRF_AUDIT_TRAIL_PG_AUDIT",
    DEFAULT_DRF_AUDIT_TRAIL_PG_AUDIT,
)
