# DRF Audit Trail

A reusable Django DRF application for auditing requests, logins, and custom processes.

---

## Features

- HTTP request auditing (`RequestAuditEvent`)
- Login and logout auditing (`LoginAuditEvent`)
- Custom process auditing (`ProcessAuditEvent`, `StepAuditEvent`, `RegistrationAuditEvent`)
- Integration with SimpleJWT
- Django Async support
- Thread safe
- Error and stacktrace tracking
- PDF report generation

---

## Installation

```sh
pip install drf-audit-trail
```

---

## Configuration

In your `settings.py`:

```python
INSTALLED_APPS = [
    ...
    "drf_audit_trail",
]

MIDDLEWARE = [
    ...
    "drf_audit_trail.middleware.RequestLoginAuditEventMiddleware",
]
```

### Database

You can use a separate database for audit data:

```python
DATABASES = {
    "default":  {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    "audit_trail": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "audit_trail.sqlite3",
    },
}

DRF_AUDIT_TRAIL_DATABASE_ALIAS = "audit_trail"  # Audit database alias
DJANO_DEFAULT_DATABASE_ALIAS = "default"  # Default database alias

DATABASE_ROUTERS = ["drf_audit_trail.database_router.DRFAuditTrail"]
```

---

## Available Settings

Add to your `settings.py` as needed:

```python
DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS = [r"^(?!/admin/jsi18n/).*$"]  # Monitored URLs (regex)
DRF_AUDIT_TRAIL_AUTH_URL = [
    "/api/token/",
    "/admin/login/",
    "/api/logout/",
    "/admin/logout/",
]  # Authentication endpoints
DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FAILED = 401  # Auth failure status code
DRF_AUDIT_TRAIL_NOTSAVE_REQUEST_BODY_URLS = ['/api/token']  # Endpoints that do not save request body
DRF_AUDIT_TRAIL_USER_PK_NAME = "pk"  # User PK field name
```

All settings are optional and have sensible defaults.

---

## Audit Models

- **RequestAuditEvent:** HTTP request auditing.
- **LoginAuditEvent:** Login/logout auditing.
- **ProcessAuditEvent:** Custom process auditing.
- **StepAuditEvent:** Process step auditing.
- **RegistrationAuditEvent:** Execution registration for each step.

---

## Example Usage in a View

```python
from rest_framework.views import APIView
from rest_framework.response import Response

class TestAPIView(APIView):
    def get(self, request, *args, **kwargs):
        drf_request_audit_event = request.META.get("drf_request_audit_event")
        drf_request_audit_event["extra_informations"] = {
            "data": "Example of extra information"
        }
        return Response("ok")
```

---

## Diagrams

### Audit Flow
![Flow](https://github.com/Talismar/drf-audit-trail/blob/develop/docs/flow.png?raw=true)

### ERD
![ERD](https://github.com/Talismar/drf-audit-trail/blob/develop/docs/DER.png?raw=true)

### Middleware Class Diagram
![Middleware Class Diagram](https://github.com/Talismar/drf-audit-trail/blob/develop/docs/middleware_class_diagram.png?raw=true)

---

## Example: Process Auditing

To audit custom business processes, use the process audit utilities:

```python
from drf_audit_trail.models import (
    ProcessAuditEvent,
    RegistrationAuditEvent,
    StepAuditEvent,
)
from drf_audit_trail.process_audit import ProcessAudit


class CreateProductProcessAudit(ProcessAudit):
    def create_process(self) -> ProcessAuditEvent:
        return self.save_model(ProcessAuditEvent(name="Criar produto"))

    def create_steps(self, process: ProcessAuditEvent):
        self.step_validation = self.save_model(
            StepAuditEvent(
                name="Validação dos Dados",
                order=1,
                process=process,
                total_registrations=2,
            )
        )

        self.step_save_db = self.save_model(
            StepAuditEvent(
                name="Salvar no banco de dados",
                order=2,
                process=process,
            )
        )

    def create_registration_step_validation_code(
        self, success, name=None, **extra_fields
    ):
        name = name or "Codigo do produto validados com sucesso"
        return self.save_model(
            RegistrationAuditEvent(
                name=name, step=self.step_validation, success=success, **extra_fields
            )
        )

    def create_registration_step_validation(self, success, name=None, **extra_fields):
        name = name or "Dados de criação validados com sucesso"
        return self.save_model(
            RegistrationAuditEvent(
                name=name, step=self.step_validation, success=success, **extra_fields
            )
        )

    def create_registration_save_db(self, success, name=None, **extra_fields):
        name = name or "Salvar no banco de dados"
        return self.save_model(
            RegistrationAuditEvent(
                step=self.step_save_db, success=success, name=name, **extra_fields
            )
        )


class ProductViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def create(self, request, *args, **kwargs):
        process_audit = CreateProductProcessAudit(request)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            process_audit.create_registration_step_validation_code(True)
            process_audit.create_registration_step_validation(True)
        else:
            if serializer.errors.get("code") is not None:
                process_audit.create_registration_step_validation_code(
                    False,
                    "Error de validação de codigo",
                    description=json.dumps(serializer.errors.get("code")),
                )
            validation_errors = json.dumps(serializer.errors)
            process_audit.create_registration_step_validation(
                False, "Erros de validação", description=validation_errors
            )
            raise ValidationError(serializer.errors)

        try:
            self.perform_create(serializer)
            process_audit.create_registration_save_db(True)
        except BaseException as e:
            process_audit.create_registration_save_db(False, e.__str__())
            raise

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)
```

## License

MIT License

---

## Notes

- All settings are optional and have default values.
- For advanced customization, see the code and docstrings.
- For questions, check the docstrings or open an issue.

---








# DRF Audit Trail

A reusable Django [DRF] application that handles auditing of requests and logins.

## Features

- Request audit trail
- Logins audit trail
- Integration with simplejwt
- Support for Django Async
- Thread Safe
- Error tracking

## Usage

To use this app, you need to install it, add it to the Django INSTALLED_APPS, and configure the middleware in your Django settings.

### Installation
```sh
pip install drf-audit-trail
```

### Configuration

Add to Django INSTALLED_APPS

```python
# settings.py

INSTALLED_APPS = [
    ...
    "drf_audit_trail",
]
```

#### Configure the middleware

Add to Django MIDDLEWARE configuration

```python
# settings.py

MIDDLEWARE = [
    ...
    "drf_audit_trail.middleware.RequestLoginAuditEventMiddleware",
]
```

## Settings

In your settings.py, configure

**DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS**:
A list that accepts regex patterns indicating which URLs should be tracked.

Example:

Default: [r"^/api/.*?/"]

```python
DRF_AUDIT_TRAIL_REQUEST_AUDIT_URLS = [r"^/api/.*?/"]
```

This means that all requests starting with /api/ will be tracked.

---

**DRF_AUDIT_TRAIL_AUTH_URL**: The endpoint used to authenticate users.

Default: /api/token/

```python
DRF_AUDIT_TRAIL_AUTH_URL = "/api/token/"
```

---

**DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FAILED**: The status code returned when the auth request failed

Default: 401

```python
DRF_AUDIT_TRAIL_AUTH_STATUS_CODE_FAILED = 401
```

## Flow
![DER](https://github.com/Talismar/drf-audit-trail/blob/develop/docs/flow.png?raw=True)

## DER
![DER](https://github.com/Talismar/drf-audit-trail/blob/develop/docs/DER.png?raw=True)

## RequestLoginAuditEventMiddleware class diagram
![DER](https://github.com/Talismar/drf-audit-trail/blob/develop/docs/middleware_class_diagram.png?raw=True)

