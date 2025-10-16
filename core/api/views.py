from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from core.process_audit import CreateProductProcessAudit, DeleteProductProcessAudit
from core.api.serializers import ProductSerializer
from core.models import Product
from rest_framework.viewsets import ModelViewSet
import json
from rest_framework.serializers import ValidationError


class ProductViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def create(self, request, *args, **kwargs):
        process_audit = CreateProductProcessAudit(request)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            process_audit.create_registration_step_validation_code(True)
            process_audit.create_registration_step_validation(True)
        else:
            if serializer.errors.get("code") is not None:
                process_audit.create_registration_step_validation_code(
                    False,
                    "Error de validação de codigo",
                    description=json.dumps(serializer.errors.get("code")),
                )
            validation_errors = json.dumps(serializer.errors)
            process_audit.create_registration_step_validation(
                False, "Erros de validação", description=validation_errors
            )
            raise ValidationError(serializer.errors)

        try:
            self.perform_create(serializer)
            process_audit.create_registration_save_db(True)
        except BaseException as e:
            process_audit.create_registration_save_db(False, e.__str__())
            raise

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)

    def destroy(self, request, pk, *args, **kwargs):
        proccess_audit = DeleteProductProcessAudit(request)
        try:
            instance = self.get_object()
            proccess_audit.create_registration_step_get_db(True)
        except BaseException as e:
            proccess_audit.create_registration_step_get_db(
                False,
                "Error ao buscar produto com o id: %s " % pk,
                description=e.__str__(),
            )
            raise

        try:
            self.perform_destroy(instance)
            proccess_audit.create_registration_save_db(True)
        except BaseException as e:
            proccess_audit.create_registration_save_db(
                False, "Error ao efetuar a ação de deletar", description=e.__str__()
            )
            raise
        return Response(status=204)

    @action(
        methods=["post"],
        detail=False,
        url_path=r"reset_password/(?P<uidb64>\w+)/(?P<token>[\w\.-]+)",
        permission_classes=[AllowAny],
    )
    def reset_password(self, request, uidb64, token):
        return Response({"uidb64": uidb64, "token": token})


class TestAPIView(APIView):

    def get(self, request: Request, *args, **kwargs):
        drf_request_audit_event = request.META.get("drf_request_audit_event")
        # data = serializers.serialize("json", Test.objects.all(), cls=DjangoJSONEncoder)
        drf_request_audit_event["extra_informations"] = {
            "data": "Sdlasd lasdk jasldkasd asldkajsldka sjdlakjsd"
        }
        return Response("asdasd")

    def post(self, request: Request, *args, **kwargs):
        return Response("Não foi possível criar", 400)
