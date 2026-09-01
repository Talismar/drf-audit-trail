# Project Context For Future Agents

## What This Repository Is

This is a Django/DRF project and reusable package named `drf_audit_trail`.
It provides audit trail models, middleware, admin exports, and a
PostgreSQL trigger-based object/field-level audit system.

The current sample app is `core`. It contains `Product`, `Supplier`, and
`Category` models and example DRF views used to demonstrate audit behavior.

Primary audit models live in `drf_audit_trail.models`:

- `RequestAuditEvent`: stores request-level metadata.
- `LoginAuditEvent`: stores auth/login/logout events.
- `ProcessAuditEvent`, `StepAuditEvent`, `RegistrationAuditEvent`: process flow
  audit entities.

Audit data is routed to the `audit_trail` database through
`drf_audit_trail.database_router.DRFAuditTrail`.

## Object/Field-Level Audit: `pg_audit_models`

Object and field-level change tracking (who changed which field, old/new
value, reason for change) is handled exclusively by the
`drf_audit_trail.pg_audit_models` app. It uses PostgreSQL triggers to write
one `ActionLog` row per action plus one `DiffLog` row per changed column.
Because capture happens in the database, it covers ORM writes, bulk
operations, and raw SQL alike, without requiring any code change on the
audited model.

Configure it via `DRF_AUDIT_TRAIL_PG_AUDIT` in settings (`models` allowlist,
`audit_all_models`, actor/role/extra-information getters, etc.). See the
README's "PostgreSQL Trigger Audit Models" section for the full settings
reference and setup steps (`sync_pg_audit_triggers` management command).

`core.Product` and `core.Supplier` are listed in the sample project's
`DRF_AUDIT_TRAIL_PG_AUDIT["models"]` (`config/settings.py`) purely as demo
coverage; they are otherwise plain Django models with no audit-specific base
class or mixin.

## Removed: `AuditLogEntry`, `@audit_log`, `manager_audit`

As of version 0.6.0, the `AuditLogEntry` model and everything that existed
only to populate it were removed in favor of `pg_audit_models`:

- The `AuditLogEntry` model (`drf_audit_trail/models/audit_log_entry.py`) and
  its table (dropped via migration `0006_delete_auditlogentry`).
- The `@audit_log` decorator and `record_system_event` (formerly
  `drf_audit_trail/audit_log.py`).
- The `drf_audit_trail.manager_audit` package (`AuditedModel`,
  `AuditedManager`, `AuditedQuerySet`, `audit_model_context`,
  `disable_manager_audit`, `set_audit_reason`).
- The `DRF_AUDIT_TRAIL_MANAGER_AUDIT` and `DRF_AUDIT_TRAIL_USER_ROLE_GETTER`
  settings, which only that code read.

Do not reintroduce these unless explicitly asked. If you see references to
them in git history, old branches, or stale documentation, that content
predates the removal.

## Current Example App State

`core.models.Product` and `core.models.Supplier` are plain `models.Model`
subclasses. `core/admin.py` registers them with normal `ModelAdmin` classes.
`core/api/views.py` exposes plain `ModelViewSet`s for both — no explicit
audit wiring is needed in view code; trigger-based audit coverage comes from
`DRF_AUDIT_TRAIL_PG_AUDIT["models"]`.

Existing DRF examples are in:

- `core/api/serializers.py`
- `core/api/views.py`
- `config/api_router.py`
- `config/urls.py`

## Validation Commands

Tests live under `drf_audit_trail/tests/`.

```bash
venv/bin/python manage.py test drf_audit_trail
venv/bin/python manage.py makemigrations --check --dry-run
```

If a new model is added, creating migrations for `core` may be expected. Do
not create migrations for `drf_audit_trail` unless the package models are
explicitly changed.

## Coding Notes

- Keep changes focused and avoid refactoring unrelated code.
- Prefer `pg_audit_models` (`DRF_AUDIT_TRAIL_PG_AUDIT["models"]` /
  `audit_all_models`) over any model-specific audit mixin for new
  object/field-level audit coverage.
