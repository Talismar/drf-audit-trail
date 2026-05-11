from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

from core.api.views import (
    AuditLogProductAPIView,
    AuditLogProductGenericUpdateView,
    MultiAuditLogProductView,
    audit_log_product_django_view,
    audit_log_product_user_role_django_view,
)
from drf_audit_trail.api.views import logout_api_view
from drf_audit_trail.integrations.rest_framework_simplejwt import (
    DRFAuditTrailTokenObtainPairView,
)
from drf_audit_trail.views import process_report_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("config.api_router")),
    path(
        "api/audit-log-generic-products/<int:pk>/",
        AuditLogProductGenericUpdateView.as_view(),
    ),
    path("api/audit-log-api-view-products/<int:pk>/", AuditLogProductAPIView.as_view()),
    path("audit-log-django-view-products/<int:pk>/", audit_log_product_django_view),
    path(
        "audit-log-django-view-products/<int:pk>/with-user-role/",
        audit_log_product_user_role_django_view,
    ),
    path(
        "api/multi-audit-log-products/<int:pk>/",
        MultiAuditLogProductView.as_view(),
    ),
    path("process_report/", process_report_view),
    path(
        "api/token/",
        DRFAuditTrailTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/logout/", logout_api_view),
]
