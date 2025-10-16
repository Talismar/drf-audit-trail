import re
from time import time
from traceback import format_exc as traceback_format_exc

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin

from drf_audit_trail.models import LoginAuditEvent, RequestAuditEvent
from drf_audit_trail.settings import (
    DRF_AUDIT_TRAIL_AUTH_URL,
    DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS,
)


class RequestLoginAuditEventMiddleware(MiddlewareMixin):
    def _start_request(self, request):
        request_audit_event_enabled = self._is_request_audit_enabled(request)

        request.META["drf_request_audit_event"] = {}
        request.META["drf_login_audit_event"] = {}
        request.META["drf_audit_trail_request_start_time"] = time()

        return request_audit_event_enabled

    async def __acall__(self, request):
        request_audit_event_enabled = self._start_request(request)

        response = await self.get_response(request)
        if request_audit_event_enabled:
            await sync_to_async(self._create_instances, thread_sensitive=True)(
                request, response
            )

        return response

    def process_request(self, request: HttpRequest):
        request_audit_event_enabled = self._start_request(request)

        raw_body = request.body
        request._body = raw_body

        response = self.get_response(request)
        if request_audit_event_enabled:
            self._create_instances(request, response)

        return response

    def process_exception(self, request, exception: BaseException):
        request.META["drf_request_audit_event"] = {
            "error_type": exception.__class__.__name__,
            "error_message": str(exception),
            "error_stacktrace": traceback_format_exc(),
        }

        if self._is_auth_url(request):
            request.META["drf_login_audit_event"]["status"] = LoginAuditEvent.FAILED

    def _create_instances(self, request, response):
        request_audit_event = RequestAuditEvent.objects.create_by_request(
            request, response
        )

        if self._is_auth_url(request) and isinstance(
            request_audit_event, RequestAuditEvent
        ):
            LoginAuditEvent.objects.create_by_request(
                request, response, request_audit_event
            )

        return response

    def _is_request_audit_enabled(self, request):
        for i in DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS:
            if bool(re.match(i, request.path)):
                return True

        return self._is_auth_url(request)

    def _is_auth_url(self, request):
        if request.method != "POST":
            return False

        def validate(auth_url):
            return auth_url == request.META.get("PATH_INFO")

        if isinstance(DRF_AUDIT_TRAIL_AUTH_URL, list):
            return any(validate(auth_url) for auth_url in DRF_AUDIT_TRAIL_AUTH_URL)

        return validate(DRF_AUDIT_TRAIL_AUTH_URL)
