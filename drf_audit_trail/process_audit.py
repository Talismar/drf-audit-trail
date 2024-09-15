from django.http import HttpRequest

from drf_audit_trail.models import ProcessAuditEvent


class ProcessAudit:
    def __init__(self, request: HttpRequest):
        self.request = request
        self._process = self.create_process()
        if not isinstance(self._process, ProcessAuditEvent):
            raise TypeError("self._process should be type ProcessAuditEvent")

        request.META["process_audit_event"] = self._process

        self.create_steps(self._process)

    def save_model(self, model):
        if self.request.user.is_authenticated:
            model.created_by = self.request.user.pk
        model.save()
        return model

    def create_process(self) -> ProcessAuditEvent:
        raise NotImplementedError()

    def create_steps(self, process: ProcessAuditEvent):
        pass
