from django.contrib import admin

from .models import Category, Product, Supplier

admin.site.register(Category)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "price")
    search_fields = ("name",)
    list_filter = ("price",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_email", "phone", "created_at", "updated_at")
    search_fields = ("name", "contact_email", "phone")
    list_filter = ("created_at", "updated_at")
