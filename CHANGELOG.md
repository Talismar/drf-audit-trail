# Changelog

## 0.5.8

### Fixed
- Removed `ProcessAuditEvent`, `RegistrationAuditEvent` and `StepAuditEvent` from the 0.5.7 read-only DB triggers. Only `LoginAuditEvent` and `RequestAuditEvent` (plus `pg_audit_models.ActionLog`/`DiffLog`) are the actual audit log and need DB-enforced immutability; the process/step/registration tables are process bookkeeping. Keeping the trigger on `ProcessAuditEvent` in particular blocked the internal `UPDATE` that `RequestAuditEventManager.create_by_request` performs to link a process to its request (via `RequestAuditEvent.processes.add(...)`). That `UPDATE` was always issued through Django's bulk related-manager path, bypassing the `ProtectedModelMixin` Python guard, and was being silently swallowed by a bare `except BaseException: pass` — except that in PostgreSQL a failed statement aborts the whole transaction, so every subsequent query in that request/test transaction failed with `TransactionManagementError`.
- Wrapped the process-linking call in `RequestAuditEventManager.create_by_request` in its own savepoint (`transaction.atomic()`) so a failure there can never poison the caller's outer transaction again.

## 0.6.0

### Removed
- **Breaking:** Removed the `AuditLogEntry` model and its migration (`0006_delete_auditlogentry`). The `@audit_log` decorator, `record_system_event`, and the `drf_audit_trail.manager_audit` package (`AuditedModel`, `AuditedManager`, `AuditedQuerySet`, `audit_model_context`, `disable_manager_audit`, `set_audit_reason`) are removed along with it, since they existed only to populate that model. `DRF_AUDIT_TRAIL_MANAGER_AUDIT` and `DRF_AUDIT_TRAIL_USER_ROLE_GETTER` settings no longer have any effect.
- Object/field-level audit tracking is now handled exclusively by `drf_audit_trail.pg_audit_models` (PostgreSQL trigger-based `ActionLog`/`DiffLog`). Projects that relied on `AuditLogEntry` should migrate to that app.

## 0.3.9 - 2025-10-01

### Added
- Automatic truncation for oversized fields in audit events (e.g., `url`, `query_params` in `RequestAuditEvent`).
- When a value exceeds the database limit (e.g., 2048 characters), it is truncated and a warning is logged to `drf_audit_trail.truncation`.
- This prevents `DataError`/`StringDataRightTruncation` exceptions and ensures the audit middleware never causes a request to fail due to excessive data size.
- Documentation updated to explain the new truncation and logging behavior.

### Fixed
- Robustness for APIs with long URLs or query parameters.

---

See the README for details and usage examples.
