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
DRF_AUDIT_TRAIL_USER_ROLE_GETTER = getattr(
    settings,
    "DRF_AUDIT_TRAIL_USER_ROLE_GETTER",
    "drf_audit_trail.utils.get_user_role_by_django_groups",
)
DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_IDENTIFIER = getattr(
    settings, "DRF_AUDIT_TRAIL_DEFAULT_SYSTEM_ACTOR_IDENTIFIER", "system"
)
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
DEFAULT_DRF_AUDIT_TRAIL_MANAGER_AUDIT = {
    "enabled": True,
    "excluded_apps": ["drf_audit_trail"],
    "default_fields": "__all__",
    "default_exclude_fields": ["created_at", "updated_at"],
    "reason_for_change_key": "reason_for_change",
    "default_reason": None,
    "default_reason_getter": None,
    "default_extra_informations_getter": None,
    "default_value_serializer": "raw",
    "foreign_key_value_serializer": "repr",
    "file_value_serializer": "name",
    "image_value_serializer": "name",
    "field_value_serializers": {},
    "default_action_descriptions": {
        "create": "Created object",
        "update": "Updated object",
        "delete": "Deleted object",
    },
    "models": {},
}
DRF_AUDIT_TRAIL_MANAGER_AUDIT = getattr(
    settings,
    "DRF_AUDIT_TRAIL_MANAGER_AUDIT",
    DEFAULT_DRF_AUDIT_TRAIL_MANAGER_AUDIT,
)
