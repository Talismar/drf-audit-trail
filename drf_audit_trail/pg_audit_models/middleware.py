from django.utils.deprecation import MiddlewareMixin

from . import audit


class PGAuditModelsMiddleware(MiddlewareMixin):
    def process_request(self, request):
        with audit(request=request):
            response = self.get_response(request)
        return response
