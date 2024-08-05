from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Test


class TestAPIView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request: Request, *args, **kwargs):
        drf_request_audit_event = request.META.get("drf_request_audit_event")
        drf_request_audit_event["extra_informations"] = {"talismar": True}

        # test = Test.objects.all()
        return Response("asdasd")
