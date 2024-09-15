from rest_framework import serializers

from core.models import Product


class ProductSerializer(serializers.ModelSerializer):
    code = serializers.CharField()

    class Meta:
        model = Product
        fields = "__all__"
