import re
from json import dumps as json_dumps
from time import time
from traceback import format_exc as traceback_format_exc

from django.db import transaction
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin

from drf_audit_trail.models import LoginAuditEvent, RequestAuditEvent
from drf_audit_trail.settings import (
    DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FALIED,
    DRF_AUDIT_TRAIL_AUTH_URL,
    DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS,
)
from drf_audit_trail.utils import (
    get_authenticated_user_by_request,
    get_ip_addresses,
    get_response_size,
)


class RequestLoginAuditEventMiddleware(MiddlewareMixin):
    def __init__(self, get_response):
        super().__init__(get_response)

        self.drf_request_audit_event = {}
        self.drf_login_audit_event = {}
        self._request_audit_event_enabled = False

        self._start_time = None
        self._url = None
        self._method = None
        self._query_params = None
        self._ip_addresses = None
        self._schema = None

    def process_request(self, request: HttpRequest):
        self.__reset()

        self._schema = request.scheme
        self._url = request.path
        self._method = request.method
        self._query_params = request.META.get("QUERY_STRING")
        self._ip_addresses = get_ip_addresses(request)

        if self.__is_auth_url(request):
            self._request_audit_event_enabled = True
        else:
            for i in DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS:
                if bool(re.match(i, self._url)):
                    self._request_audit_event_enabled = True
                    break

        self._start_time = time()
        request.META["drf_audit_event_start_time"] = self._start_time

        return self.get_response(request)

    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        if self._request_audit_event_enabled:
            request.META["drf_request_audit_event"] = self.drf_request_audit_event
            request.META["drf_login_audit_event"] = self.drf_login_audit_event

    def process_response(self, request, response):
        if self._request_audit_event_enabled:
            authenticated_user = self.__get_authenticated_user(request)
            extra_informations = self._get_extra_informations(
                self.drf_request_audit_event
            )

            with transaction.atomic():
                request_audit_event_instance = RequestAuditEvent.objects.create(
                    url=self._url,
                    method=self._method,
                    query_params=self._query_params,
                    ip_addresses=self._ip_addresses,
                    request_type=self._schema,
                    user=authenticated_user,
                    response_time=time() - self._start_time,
                    response_size=get_response_size(response),
                    status_code=getattr(response, "status_code"),
                    error_type=self.drf_request_audit_event.get("error_type"),
                    error_message=self.drf_request_audit_event.get("error_message"),
                    error_stacktrace=self.drf_request_audit_event.get(
                        "error_stacktrace"
                    ),
                    extra_informations=extra_informations,
                )

                if self.__is_auth_url(request):
                    extra_informations = self._get_extra_informations(
                        self.drf_login_audit_event
                    )

                    LoginAuditEvent.objects.create(
                        extra_informations=extra_informations,
                        status=self._get_login_status(request, response),
                        request=request_audit_event_instance,
                    )

        return response

    def process_exception(self, request, exception: BaseException):
        self.drf_request_audit_event["error_type"] = exception.__class__.__name__
        self.drf_request_audit_event["error_message"] = str(exception)
        self.drf_request_audit_event["error_stacktrace"] = traceback_format_exc()

        if self.__is_auth_url(request):
            self.drf_login_audit_event["status"] = LoginAuditEvent.FAILED

    def _get_extra_informations(self, instance_dict: dict):
        request_extra_informations = instance_dict.get("extra_informations")
        extra_informations = None

        if request_extra_informations is not None:
            try:
                extra_informations = json_dumps(request_extra_informations)
            except Exception:
                pass

        return extra_informations

    def _get_login_status(self, request, response):
        if response.status_code == DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FALIED:
            return LoginAuditEvent.FAILED

        if self.drf_login_audit_event.get("status") is None:
            if request.user.is_authenticated:
                return LoginAuditEvent.SIGNIN
            else:
                return LoginAuditEvent.FAILED

        return self.drf_login_audit_event.get("status")

    def __reset(self):
        self.drf_request_audit_event = {}
        self.drf_login_audit_event = {}
        self._request_audit_event_enabled = False

    def __is_auth_url(self, request):
        return DRF_AUDIT_TRAIL_AUTH_URL == request.META.get("PATH_INFO")

    def __get_authenticated_user(self, request):
        if self.__is_auth_url(request):
            return self.drf_request_audit_event.get("user")

        return get_authenticated_user_by_request(request)
