from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

from drf_audit_trail.api.views import logout_api_view
from drf_audit_trail.integrations.rest_framework_simplejwt import (
    DRFAuditTrailTokenObtainPairView,
)
from drf_audit_trail.views import process_report_view


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("config.api_router")),
    path("process_report/", process_report_view),
    path(
        "api/token/",
        DRFAuditTrailTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/logout/", logout_api_view),
]
