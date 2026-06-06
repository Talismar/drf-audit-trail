import io
import json
import logging
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import (
    Client,
    RequestFactory,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse
from rest_framework_simplejwt.tokens import AccessToken

from core.models import Product, Supplier
from drf_audit_trail.audit_log import audit_log, record_system_event
from drf_audit_trail.manager_audit import (
    audit_model_context,
    disable_manager_audit,
    set_audit_reason,
)
from drf_audit_trail.middleware.request_login_audit_event import (
    RequestLoginAuditEventMiddleware,
)
from drf_audit_trail.models import (
    AuditLogEntry,
    LoginAuditEvent,
    ProcessAuditEvent,
    RequestAuditEvent,
)
from drf_audit_trail.utils import deserialize_audit_value


def get_custom_test_user_role(user, request=None):
    return f"custom:{user.username}"


def get_manager_audit_extra_informations(
    *,
    instance,
    action,
    field_name=None,
    old_raw_value=None,
    new_raw_value=None,
    **kwargs,
):
    data = {
        "scope": instance._meta.label_lower,
        "object_id": instance.pk,
        "action": action,
    }
    if field_name is not None:
        data["field_name"] = field_name
    if old_raw_value is not None:
        data["old_raw_value"] = old_raw_value
    if new_raw_value is not None:
        data["new_raw_value"] = new_raw_value
    return data


def get_manager_audit_model_extra_informations(*, instance, action, **kwargs):
    return {
        "scope": "model-specific",
        "object_id": instance.pk,
        "action": action,
        "model_getter": True,
    }


MANAGER_AUDIT_PRODUCT_SETTINGS = {
    "enabled": True,
    "default_fields": "__all__",
    "default_exclude_fields": ["created_at", "updated_at"],
    "default_reason": None,
    "default_action_descriptions": {
        "create": "Created object",
        "update": "Updated object",
        "delete": "Deleted object",
    },
    "models": {
        "core.Product": {
            "fields": ["name", "code", "price", "quantity"],
            "exclude_fields": [],
            "require_reason": False,
            "action_descriptions": {
                "create": "Created product",
                "update": "Updated product",
                "delete": "Deleted product",
            },
        }
    },
}

MANAGER_AUDIT_SUPPLIER_SETTINGS = {
    **MANAGER_AUDIT_PRODUCT_SETTINGS,
    "models": {
        "core.Supplier": {
            "fields": ["name", "contact_email", "phone", "notes"],
            "exclude_fields": [],
            "require_reason": False,
            "action_descriptions": {
                "create": "Created supplier",
                "update": "Updated supplier",
                "delete": "Deleted supplier",
            },
        }
    },
}


