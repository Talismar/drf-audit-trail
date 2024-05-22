from django.contrib import admin

from .models import LoginAuditEvent, RequestAuditEvent


class RequestAuditEventModelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "method",
        "url",
        "status_code",
        "user",
        "datetime",
        "request_type",
    )
    list_filter = ("method", "ip_addresses")
    search_fields = ("method", "ip_addresses", "status_code")


admin.site.register(RequestAuditEvent, RequestAuditEventModelAdmin)


class LoginAuditEventModelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "datetime",
        "request_ip_addresses",
        "request__status_code",
    )
    list_filter = ("status",)

    @admin.display()
    def request_ip_addresses(self, obj):
        if obj.request is not None:
            return obj.request.ip_addresses

    @admin.display()
    def request__status_code(self, obj):
        if obj.request is not None:
            return obj.request.status_code

    def user(self, obj):
        if obj.request is not None:
            return obj.request.user


admin.site.register(LoginAuditEvent, LoginAuditEventModelAdmin)
