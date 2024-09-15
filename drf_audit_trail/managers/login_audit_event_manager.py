from django.db import transaction
from django.db.models import Manager

from drf_audit_trail.settings import DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FALIED
from drf_audit_trail.utils import get_extra_informations


class LoginAuditEventManager(Manager):
    def create_by_request(self, request, response, request_audit_event):
        request_meta = getattr(request, "META")
        drf_login_audit_event = request_meta.get("drf_login_audit_event", {})
        status = None

        if response.status_code == DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FALIED:
            status = "Failed"
        elif not drf_login_audit_event.get("status"):
            status = "Sign in" if request.user.is_authenticated else "Failed"
        else:
            status = drf_login_audit_event.get("status")

        extra_informations = get_extra_informations(drf_login_audit_event)

        with transaction.atomic():
            return self.create(
                status=status,
                request=request_audit_event,
                extra_informations=extra_informations,
            )
