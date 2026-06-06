import json

from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.api.serializers import ProductSerializer, SupplierSerializer
from core.models import Product, Supplier
from core.process_audit import CreateProductProcessAudit, DeleteProductProcessAudit
from drf_audit_trail.manager_audit import audit_model_context


def get_reason_for_change(request):
    reason_for_change = None
    try:
        reason_for_change = request.data.get("reason_for_change")
    except Exception:
        reason_for_change = None

    if reason_for_change is None:
        reason_for_change = request.query_params.get("reason_for_change")

    return reason_for_change


class ProductViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        with audit_model_context(
            request=self.request,
            action_description="Created product through API",
            model=Product,
        ):
            serializer.save()

    def perform_update(self, serializer):
        with audit_model_context(
            request=self.request,
            action_description="Updated product through API",
            model=Product,
        ):
            serializer.save()

    def perform_destroy(self, instance):
        with audit_model_context(
            request=self.request,
            action_description="Deleted product through API",
            model=instance,
            reason_for_change=get_reason_for_change(self.request),
        ):
            instance.delete()

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


class SupplierViewSet(ModelViewSet):
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.all()
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        with audit_model_context(
            request=self.request,
            action_description="Created supplier through API",
            model=Supplier,
        ):
            serializer.save()

    def perform_update(self, serializer):
        with audit_model_context(
            request=self.request,
            action_description="Updated supplier through API",
            model=Supplier,
        ):
            serializer.save()

    def perform_destroy(self, instance):
        with audit_model_context(
            request=self.request,
            action_description="Deleted supplier through API",
            model=instance,
            reason_for_change=get_reason_for_change(self.request),
        ):
            instance.delete()

    @action(methods=["post"], detail=True, url_path="update-notes")
    def update_notes(self, request, pk=None):
        if "notes" not in request.data:
            raise ValidationError({"notes": "This field is required."})

        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            data={
                "notes": request.data.get("notes"),
                "reason_for_change": get_reason_for_change(request),
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        with audit_model_context(
            request=request,
            action_description="Updated supplier notes",
            model=instance,
            fields=["notes"],
        ):
            serializer.save()

        return Response(self.get_serializer(instance).data)


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


class ProductPriceUpdateView(APIView):
    permission_classes = [AllowAny]

    def patch(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        serializer = ProductSerializer(
            product,
            data={
                "price": request.data.get("price"),
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        with audit_model_context(
            request=request,
            action_description="Updated product price through API",
            model=product,
            fields=["price"],
        ):
            serializer.save()

        return Response(ProductSerializer(product).data)
