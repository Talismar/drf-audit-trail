from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.response import Response

from drf_audit_trail.models import LoginAuditEvent


class DRFAuditTrailTokenAuthentication(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        drf_login_audit_event = request.META.get("drf_login_audit_event")
        drf_request_audit_event = request.META.get("drf_request_audit_event")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        drf_login_audit_event["status"] = LoginAuditEvent.SIGNIN
        drf_request_audit_event["user"] = user

        token, created = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})
