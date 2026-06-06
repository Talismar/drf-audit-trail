from django.db import models

from drf_audit_trail.manager_audit import AuditedModel


class Product(AuditedModel):

    FIELD_UPDATE_ACTION_DESCRIPTIONS = {
        "name": "Product name updated",
        "code": "Product code updated",
        "price": "Product price updated",
        "quantity": "Product quantity updated",
    }

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=255, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return "%i | %s" % (self.pk, self.name)


class Supplier(AuditedModel):
    name = models.CharField(max_length=255)
    contact_email = models.EmailField(max_length=255)
    phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return "%i | %s" % (self.pk, self.name)
