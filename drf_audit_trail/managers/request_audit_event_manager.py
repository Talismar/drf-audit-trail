from time import time

from django.db import transaction
from django.db.models import Manager

from drf_audit_trail.utils import (
    get_authenticated_user_by_request,
    get_ip_addresses,
    get_response_size,
)


class RequestAuditEventManager(Manager):
    def create_by_request_and_response(self, request, response):
        request_meta = getattr(request, "META")

        if request_meta is None or isinstance(request_meta, dict) is False:
            return

        start_time = request_meta.get("drf_audit_event_start_time")
        if start_time is None:
            return

        authenticated_user = get_authenticated_user_by_request(request)

        url = getattr(request, "path")
        method = getattr(request, "method")
        query_params = request_meta.get("QUERY_STRING")

        with transaction.atomic():
            self.create(
                url=url,
                method=method,
                query_params=query_params,
                ip_addresses=get_ip_addresses(request),
                user=authenticated_user,
                response_time=time() - start_time,
                response_size=get_response_size(response),
                status_code=getattr(response, "status_code"),
            )

    def create_by_asgi_scope(self, scope):
        pass
