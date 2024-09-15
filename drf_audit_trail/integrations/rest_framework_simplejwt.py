from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView

from drf_audit_trail.models import LoginAuditEvent


class DRFAuditTrailIntegrationMixin:
    def post(self, request, *args: tuple, **kwargs: dict):
        serializer = self.get_serializer(data=request.data)
        drf_login_audit_event = request.META.get("drf_login_audit_event")
        drf_request_audit_event = request.META.get("drf_request_audit_event")

        try:
            serializer.is_valid(raise_exception=True)
            drf_login_audit_event["status"] = LoginAuditEvent.SIGNIN
            drf_request_audit_event["user"] = serializer.user
        except TokenError as e:
            raise InvalidToken(e.args[0])

        return Response(serializer.validated_data, status=HTTP_200_OK)


class DRFAuditTrailTokenObtainPairView(
    DRFAuditTrailIntegrationMixin, TokenObtainPairView
):
    pass
