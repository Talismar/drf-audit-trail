from django.utils.deprecation import MiddlewareMixin

from . import audit


class PGAuditModelsMiddleware(MiddlewareMixin):
    async_capable = False

    def process_response(self, request, response):
        with audit(request=request):
            return response
