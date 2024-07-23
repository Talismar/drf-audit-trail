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

