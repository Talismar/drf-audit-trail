# Changelog

## Unreleased

### Added
- Automatic truncation for oversized fields in audit events (e.g., `url`, `query_params` in `RequestAuditEvent`).
- When a value exceeds the database limit (e.g., 2048 characters), it is truncated and a warning is logged to `drf_audit_trail.truncation`.
- This prevents `DataError`/`StringDataRightTruncation` exceptions and ensures the audit middleware never causes a request to fail due to excessive data size.
- Documentation updated to explain the new truncation and logging behavior.

### Fixed
- Robustness for APIs with long URLs or query parameters.

---

See the README for details and usage examples.
