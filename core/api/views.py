import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.api.serializers import ProductSerializer
from core.models import Product
from core.process_audit import CreateProductProcessAudit, DeleteProductProcessAudit
from drf_audit_trail.audit_log import audit_log


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


class AuditLogProductViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()
    permission_classes = [AllowAny]

    @audit_log(
        event_type="Create",
        action_description="Created product using ModelViewSet",
        field_name="All fields",
    )
    def create(self, request, *args, audit_log, **kwargs):
        response = super().create(request, *args, **kwargs)

        if response.status_code == 201:
            product = Product.objects.get(pk=response.data["id"])
            audit_log.set_content_object(product)
            audit_log.new_values = response.data
            audit_log.extra_informations = {"view_type": "ModelViewSet"}

        return response

    @audit_log(
        event_type="Update",
        action_description="Updated product using ModelViewSet",
        field_name="All fields",
    )
    def update(self, request, *args, audit_log, **kwargs):
        instance = self.get_object()
        old_values = {
            "name": instance.name,
            "code": instance.code,
            "price": str(instance.price),
            "quantity": instance.quantity,
        }

        response = super().update(request, *args, **kwargs)

        instance.refresh_from_db()
        new_values = {
            "name": instance.name,
            "code": instance.code,
            "price": str(instance.price),
            "quantity": instance.quantity,
        }

        audit_log.set_content_object(instance)
        audit_log.old_values = old_values
        audit_log.new_values = new_values
        audit_log.reason_for_change = request.data.get(
            "reason_for_change", "Product update through ModelViewSet"
        )
        audit_log.extra_informations = {"view_type": "ModelViewSet"}

        return response


class AuditLogProductGenericUpdateView(generics.UpdateAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()
    permission_classes = [AllowAny]

    @audit_log(
        event_type="Update",
        action_description="Updated product using GenericAPIView",
        field_name="price",
    )
    def patch(self, request, *args, audit_log, **kwargs):
        instance = self.get_object()
        old_price = instance.price

        response = super().patch(request, *args, **kwargs)

        instance.refresh_from_db()
        audit_log.set_content_object(instance)
        audit_log.old_values = {"price": str(old_price)}
        audit_log.new_values = {"price": str(instance.price)}
        audit_log.reason_for_change = request.data.get("reason_for_change")
        audit_log.extra_informations = {"view_type": "GenericAPIView"}

        return response


class AuditLogProductAPIView(APIView):
    permission_classes = [AllowAny]

    @audit_log(
        event_type="View",
        action_description="Viewed product using APIView",
    )
    def get(self, request, pk, audit_log):
        product = get_object_or_404(Product, pk=pk)
        audit_log.set_content_object(product)
        audit_log.extra_informations = {
            "view_type": "APIView",
            "product_snapshot": ProductSerializer(product).data,
        }

        return Response(ProductSerializer(product).data)


@audit_log(
    event_type="View",
    action_description="Viewed product using Django view",
)
def audit_log_product_django_view(request, pk, audit_log):
    product = get_object_or_404(Product, pk=pk)
    audit_log.set_content_object(product)
    response_data = {
        "id": product.pk,
        "name": product.name,
        "code": product.code,
        "price": str(product.price),
        "quantity": product.quantity,
    }
    audit_log.extra_informations = {
        "view_type": "Django view",
        "product_snapshot": response_data,
    }

    return JsonResponse(response_data)


@audit_log(
    event_type="View",
    action_description="Viewed product using Django view with user role",
)
def audit_log_product_user_role_django_view(request, pk, audit_log):
    product = get_object_or_404(Product, pk=pk)
    audit_log.set_content_object(product)
    response_data = {
        "id": product.pk,
        "name": product.name,
        "code": product.code,
    }
    audit_log.extra_informations = {
        "view_type": "Django view",
        "role_source": "groups",
        "product_snapshot": response_data,
    }

    return JsonResponse(response_data)


class MultiAuditLogProductView(APIView):
    """
    - audit_log_view: registra o acesso (View) ao produto — acessível pelo
      parâmetro `audit_log_view`.
    - audit_log_price_update: registra a alteração de preço (Update) — acessível
      pelo parâmetro `audit_log_price`.
    """

    permission_classes = [AllowAny]

    @audit_log(
        event_type="View",
        action_description="Viewed product for price update preview",
        parameter_name="audit_log_view",
    )
    @audit_log(
        event_type="Update",
        action_description="Updated product price",
        field_name="price",
        parameter_name="audit_log_price",
    )
    def patch(self, request, pk, audit_log_view, audit_log_price):
        product = get_object_or_404(Product, pk=pk)
        old_price = product.price

        # enriquece o log de visualização
        audit_log_view.set_content_object(product)
        audit_log_view.extra_informations = {
            "note": "snapshot before price update",
            "product_snapshot": ProductSerializer(product).data,
        }

        # aplica a atualização de preço
        new_price = request.data.get("price", old_price)
        product.price = new_price
        product.save(update_fields=["price"])

        # enriquece o log de alteração
        audit_log_price.set_content_object(product)
        audit_log_price.old_values = {"price": str(old_price)}
        audit_log_price.new_values = {"price": str(product.price)}
        audit_log_price.reason_for_change = request.data.get("reason_for_change")

        return Response({"id": product.pk, "price": str(product.price)})
