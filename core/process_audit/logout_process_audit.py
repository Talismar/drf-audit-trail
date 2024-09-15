from drf_audit_trail.models import (
    ProcessAuditEvent,
    RegistrationAuditEvent,
    StepAuditEvent,
)
from drf_audit_trail.process_audit import ProcessAudit


class LogoutProcessAudit(ProcessAudit):
    def create_process(self) -> ProcessAuditEvent:
        return ProcessAuditEvent.objects.create(
            name="Usuário sair",
            description="Processo de registrar quando usuário saiu do sistema",
        )

    def create_steps(self, process: ProcessAuditEvent):
        self.etapa_criacao = StepAuditEvent.objects.create(
            process=process,
            name="Criação no Banco de Dados",
            description="Criação do usuário no banco de dados",
            order=2,
        )

    def create_registration_etapa_validacao(
        self, success, message="Dados do usuário validados com sucesso"
    ):
        RegistrationAuditEvent.objects.create(
            step=self.etapa_validacao, success=success, message=message
        )

    def create_registration_etapa_criacao(
        self, success, message="Usuário criado no banco de dados"
    ):
        RegistrationAuditEvent.objects.create(
            step=self.etapa_criacao, success=success, message=message
        )
