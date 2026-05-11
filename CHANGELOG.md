# Changelog

## Unreleased

### Added
- Added `AuditLogEntry` for structured audit log rows tied optionally to `RequestAuditEvent`.
- Added `audit_log` decorator for views and `record_system_event` for request-less system actions.
- Added text-based JSON serialization for `old_values`, `new_values`, and `extra_informations`.
- Added configurable active user role resolution for `AuditLogEntry.actor_role`.

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
