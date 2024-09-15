from time import time

from django.db import transaction
from django.db.models import Manager

from drf_audit_trail.settings import DRF_AUDIT_TRAIL_USER_PK_NAME
from drf_audit_trail.utils import (
    get_authenticated_user_by_request,
    get_extra_informations,
    get_ip_addresses,
    get_response_size,
)


class RequestAuditEventManager(Manager):
    def create_by_request(self, request, response=None):
        request_meta = getattr(request, "META")
        start_time = request_meta.get("drf_audit_trail_request_start_time")
        authenticated_user = get_authenticated_user_by_request(request)

        drf_request_audit_event = request_meta.get("drf_request_audit_event", {})

        error_type = drf_request_audit_event.get("error_type")
        error_message = drf_request_audit_event.get("error_message")
        error_stacktrace = drf_request_audit_event.get("error_stacktrace")
        extra_informations = get_extra_informations(drf_request_audit_event)

        process_audit_event = request_meta.get("process_audit_event")

        instance = None
        with transaction.atomic():
            instance = self.create(
                url=request.path,
                method=request.method,
                query_params=request.META.get("QUERY_STRING"),
                ip_addresses=get_ip_addresses(request),
                request_type=request.scheme,
                user=getattr(authenticated_user, DRF_AUDIT_TRAIL_USER_PK_NAME, None),
                response_time=time() - start_time,
                response_size=get_response_size(response),
                status_code=getattr(response, "status_code", None),
                error_type=error_type,
                error_message=error_message,
                error_stacktrace=error_stacktrace,
                extra_informations=extra_informations,
            )

        if process_audit_event is not None and instance is not None:
            try:
                instance.processes.add(process_audit_event)
            except BaseException:
                pass

        return instance
