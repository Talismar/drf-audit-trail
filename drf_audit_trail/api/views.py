from rest_framework.response import Response
from rest_framework.views import APIView

from drf_audit_trail.models import (
    LoginAuditEvent,
)


class LogoutAPIView(APIView):
    def post(self, request, *args, **kwargs):
        drf_login_audit_event = request.META.get("drf_login_audit_event")
        if drf_login_audit_event is not None:
            drf_login_audit_event["status"] = LoginAuditEvent.SIGNOUT
        return Response({"detail": "Successfully logged out."})


logout_api_view = LogoutAPIView.as_view()
