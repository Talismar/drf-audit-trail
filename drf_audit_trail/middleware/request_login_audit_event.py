import re
import threading
from json import dumps as json_dumps
from time import time
from traceback import format_exc as traceback_format_exc

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.tokens import AccessToken, TokenError

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

User = get_user_model()

_thread_locals = threading.local()


class RequestLoginAuditEventMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest):
        self.__reset()
        _thread_locals.schema = request.scheme

        if isinstance(_thread_locals.schema, str) and _thread_locals.schema.startswith(
            "http"
        ):
            _thread_locals.url = request.path
            _thread_locals.method = request.method
            _thread_locals.META = request.META
            _thread_locals.query_params = _thread_locals.META.get("QUERY_STRING")
            _thread_locals.ip_addresses = get_ip_addresses(request)
            _thread_locals.META["drf_request_audit_event"] = {}
            _thread_locals.META["drf_login_audit_event"] = {}

            _thread_locals.request_audit_event_enabled = False
            for i in DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS:
                if bool(re.match(i, _thread_locals.url)):
                    _thread_locals.request_audit_event_enabled = True
                    break

            if self.__is_auth_url(request):
                _thread_locals.request_audit_event_enabled = True

            _thread_locals.start_time = time()
            _thread_locals.META["drf_audit_event_start_time"] = (
                _thread_locals.start_time
            )

    def process_response(self, request, response):
        if getattr(_thread_locals, "request_audit_event_enabled", False):
            authenticated_user = self.__get_authenticated_user(request)
            extra_informations = self._get_extra_informations(
                _thread_locals.META["drf_request_audit_event"]
            )

            with transaction.atomic():
                request_audit_event_instance = RequestAuditEvent.objects.create(
                    url=_thread_locals.url,
                    method=_thread_locals.method,
                    query_params=_thread_locals.query_params,
                    ip_addresses=_thread_locals.ip_addresses,
                    request_type=_thread_locals.schema,
                    user=authenticated_user,
                    response_time=time() - _thread_locals.start_time,
                    response_size=get_response_size(response),
                    status_code=getattr(response, "status_code", None),
                    error_type=_thread_locals.META["drf_request_audit_event"].get(
                        "error_type"
                    ),
                    error_message=_thread_locals.META["drf_request_audit_event"].get(
                        "error_message"
                    ),
                    error_stacktrace=_thread_locals.META["drf_request_audit_event"].get(
                        "error_stacktrace"
                    ),
                    extra_informations=extra_informations,
                )

                if self.__is_auth_url(request):
                    extra_informations = self._get_extra_informations(
                        _thread_locals.META["drf_login_audit_event"]
                    )
                    LoginAuditEvent.objects.create(
                        extra_informations=extra_informations,
                        status=self._get_login_status(request, response),
                        request=request_audit_event_instance,
                    )

        return response

    def process_exception(self, request, exception: BaseException):
        _thread_locals.META["drf_request_audit_event"] = {
            "error_type": exception.__class__.__name__,
            "error_message": str(exception),
            "error_stacktrace": traceback_format_exc(),
        }

        if self.__is_auth_url(request):
            _thread_locals.META["drf_login_audit_event"][
                "status"
            ] = LoginAuditEvent.FAILED

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

        if _thread_locals.META["drf_login_audit_event"].get("status") is None:
            if request.user.is_authenticated:
                return LoginAuditEvent.SIGNIN
            else:
                return LoginAuditEvent.FAILED

        return _thread_locals.META["drf_login_audit_event"].get("status")

    def __reset(self):
        _thread_locals.request_audit_event_enabled = False
        _thread_locals.start_time = None
        _thread_locals.url = None
        _thread_locals.method = None
        _thread_locals.query_params = None
        _thread_locals.ip_addresses = None
        _thread_locals.schema = None
        _thread_locals.META = dict()

    def __is_auth_url(self, request):
        # Integration to admin login | new feature
        if getattr(_thread_locals, "method") == "POST":

            def _validate(auth_url):
                return auth_url == _thread_locals.META.get("PATH_INFO")

            if isinstance(DRF_AUDIT_TRAIL_AUTH_URL, list):
                return any(_validate(auth_url) for auth_url in DRF_AUDIT_TRAIL_AUTH_URL)

            return _validate(DRF_AUDIT_TRAIL_AUTH_URL)
        return False

    def __get_authenticated_user(self, request):
        if self.__is_auth_url(request):
            return _thread_locals.META["drf_request_audit_event"].get("user")

        # return (
        #         _thread_locals.META["drf_request_audit_event"].get("user") or None
        #         if request.user.is_anonymous
        #         else request.user
        #     )

        return get_authenticated_user_by_request(
            request
        ) or self.__get_user_by_raw_authorization_header(request)

    def __get_user_by_raw_authorization_header(self, request):
        authorization_header = request.headers.get("Authorization")

        if isinstance(authorization_header, str) and "Bearer " in authorization_header:
            raw_access_token_split = authorization_header.split("Bearer ")

            if len(raw_access_token_split) == 2:
                raw_access_token = raw_access_token_split[1]

                try:
                    access_token = AccessToken(raw_access_token)
                    user_id = access_token.get("user_id")
                    return User.objects.get(pk=user_id)
                except (TokenError, User.DoesNotExist):
                    pass
