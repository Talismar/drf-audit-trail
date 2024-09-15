from drf_audit_trail.models import (
    ProcessAuditEvent,
    RegistrationAuditEvent,
    StepAuditEvent,
)
from drf_audit_trail.process_audit import ProcessAudit


class DeleteProductProcessAudit(ProcessAudit):
    def create_process(self) -> ProcessAuditEvent:
        return self.save_model(ProcessAuditEvent(name="Deletar produto"))

    def create_steps(self, process: ProcessAuditEvent):
        self.step_buscar_produto = self.save_model(
            StepAuditEvent(
                process=process,
                name="Verificar se o produto existe no banco de dados",
                order=1,
            )
        )

        self.step_save_db = self.save_model(
            StepAuditEvent(process=process, name="Deletar do banco de dados", order=2)
        )

    def create_registration_step_get_db(
        self, success, name="Produto encontrado", **extra_fields
    ):
        return self.save_model(
            RegistrationAuditEvent(
                step=self.step_buscar_produto,
                success=success,
                name=name,
                **extra_fields
            )
        )

    def create_registration_save_db(
        self, success, name="Salvar no banco de dados", **extra_fields
    ):
        return self.save_model(
            RegistrationAuditEvent(
                step=self.step_save_db, success=success, name=name, **extra_fields
            )
        )
