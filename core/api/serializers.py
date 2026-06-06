from rest_framework import serializers

from core.models import Product, Supplier


class ProductSerializer(serializers.ModelSerializer):
    code = serializers.CharField()
    reason_for_change = serializers.JSONField(
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Product
        fields = "__all__"

    def create(self, validated_data):
        validated_data.pop("reason_for_change", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("reason_for_change", None)
        return super().update(instance, validated_data)


class SupplierSerializer(serializers.ModelSerializer):
    reason_for_change = serializers.JSONField(
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Supplier
        fields = "__all__"

    def create(self, validated_data):
        validated_data.pop("reason_for_change", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("reason_for_change", None)
        return super().update(instance, validated_data)
