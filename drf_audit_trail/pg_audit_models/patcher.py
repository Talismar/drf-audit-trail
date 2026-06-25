import pkgutil
from importlib import import_module

from django.contrib import admin
from django.contrib.admin import autodiscover
from django.db.models import Model

from . import audit
from .config import (
    get_api_views_module_paths,
    get_django_views_module_paths,
    get_pg_audit_config,
    is_model_audited,
)


def decorate_method(cls, name, callback=None):
    func = getattr(cls, name)
    source = f"{cls.__module__}.{cls.__name__.lower()}.{name}"
    # Avoid double patching
    if not getattr(func, "_audit_patched", False):
        print(f"Patching action method {cls.__name__}.{name}...")
        wrapped = audit(source=source, callback=callback)(func)
        wrapped._audit_patched = True
        setattr(cls, name, wrapped)


def get_model_admin_callback(cls, request, obj, *args, **kwargs):
    pk = obj.pk if isinstance(obj, Model) else None
    return {
        "model": cls.model,
        "pk": pk,
        "request": request,
        "url": get_request_full_path(request),
    }


def patch_admin():
    config = get_pg_audit_config()
    autodiscover()
    for model, model_admin in admin.site._registry.items():
        admin_class = model_admin.__class__
        if is_model_audited(model, config):
            decorate_method(admin_class, "save_model", get_model_admin_callback)
            decorate_method(admin_class, "delete_queryset", get_model_admin_callback)
            decorate_method(admin_class, "delete_model", get_model_admin_callback)


def import_modules(module_paths):
    for module_path in module_paths:
        import_module_with_children(module_path)


def import_module_with_children(module_path):
    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name != module_path and not module_path.startswith(f"{exc.name}."):
            raise
        return

    import_child_modules(module)


def import_api_views_modules(config=None):
    config = config or get_pg_audit_config()
    import_modules(get_api_views_module_paths(config))


def import_django_views_modules(config=None):
    config = config or get_pg_audit_config()
    import_modules(get_django_views_module_paths(config))


def import_child_modules(module):
    package_paths = getattr(module, "__path__", None)
    if not package_paths:
        return

    for module_info in pkgutil.walk_packages(package_paths, f"{module.__name__}."):
        module_path = module_info.name
        try:
            import_module(module_path)
        except ModuleNotFoundError as exc:
            if exc.name != module_path and not module_path.startswith(f"{exc.name}."):
                raise


def get_all_viewsets(cls, config=None):
    import_api_views_modules(config)
    seen = set()

    def walk(cls):
        for subcls in cls.__subclasses__():
            if subcls not in seen:
                seen.add(subcls)
                yield subcls
                yield from walk(subcls)

    return list(walk(cls))


def get_model_viewset_callback(cls, request, *args, **kwargs):
    model = get_view_model(cls)
    return {
        "model": model,
        "pk": kwargs.get("pk"),
        "request": request,
        "url": get_request_full_path(request),
    }


def get_api_view_callback(cls, request, *args, **kwargs):
    model = get_view_model(cls)
    return {
        "model": model,
        "pk": kwargs.get("pk"),
        "request": request,
        "url": get_request_full_path(request),
    }


def get_django_view_callback(cls, request, *args, **kwargs):
    model = get_view_model(cls)
    return {
        "model": model,
        "pk": kwargs.get("pk"),
        "request": request,
        "url": get_request_full_path(request),
    }


def get_view_model(cls):
    explicit_model = getattr(cls, "audit_model", None) or getattr(cls, "model", None)
    if isinstance(explicit_model, type) and issubclass(explicit_model, Model):
        return explicit_model

    queryset = getattr(cls, "queryset", None)
    if queryset is not None and hasattr(queryset, "model"):
        return queryset.model

    serializer_class = getattr(cls, "serializer_class", None)
    serializer_meta = getattr(serializer_class, "Meta", None)
    return getattr(serializer_meta, "model", None)


def get_viewset_model(cls):
    return get_view_model(cls)


def get_request_full_path(request):
    if request is None:
        return None

    get_full_path = getattr(request, "get_full_path", None)
    if callable(get_full_path):
        return get_full_path()

    django_request = getattr(request, "_request", None)
    get_full_path = getattr(django_request, "get_full_path", None)
    if callable(get_full_path):
        return get_full_path()

    return None


def should_patch_viewset(cls, config=None):
    model = get_view_model(cls)
    return model is not None and is_model_audited(model, config)


def should_patch_api_view(cls, config=None):
    model = get_view_model(cls)
    return model is not None and is_model_audited(model, config)


def should_patch_django_view(cls, config=None):
    model = get_view_model(cls)
    return model is not None and is_model_audited(model, config)


def patch_viewsets():
    config = get_pg_audit_config()

    try:
        from rest_framework.decorators import MethodMapper
        from rest_framework.viewsets import ViewSetMixin
    except ImportError:
        print("Django Rest Framework is not installed.")
        return

    default_actions = set(config.get("api_views_actions") or ())

    for cls in get_all_viewsets(ViewSetMixin, config):
        if not cls or not should_patch_viewset(cls, config):
            continue

        attrs = dir(cls)
        for attr_name in default_actions:
            if attr_name in attrs:
                decorate_method(cls, attr_name, get_model_viewset_callback)

        for attr_name in attrs:
            attr = getattr(cls, attr_name)
            if hasattr(attr, "mapping") and isinstance(attr.mapping, MethodMapper):
                decorate_method(cls, attr_name, get_model_viewset_callback)


def get_all_api_views(cls, config=None):
    import_api_views_modules(config)
    seen = set()

    def walk(cls):
        for subcls in cls.__subclasses__():
            if subcls not in seen:
                seen.add(subcls)
                yield subcls
                yield from walk(subcls)

    return list(walk(cls))


def patch_api_views():
    config = get_pg_audit_config()

    try:
        from rest_framework.views import APIView
        from rest_framework.viewsets import ViewSetMixin
    except ImportError:
        print("Django Rest Framework is not installed.")
        return

    methods = set(config.get("api_views_methods") or ())

    for cls in get_all_api_views(APIView, config):
        if (
            not cls
            or issubclass(cls, ViewSetMixin)
            or not should_patch_api_view(cls, config)
        ):
            continue

        attrs = dir(cls)
        for method_name in methods:
            if method_name in attrs:
                decorate_method(cls, method_name, get_api_view_callback)


def get_all_django_views(cls, config=None):
    import_django_views_modules(config)
    seen = set()

    def walk(cls):
        for subcls in cls.__subclasses__():
            if subcls not in seen:
                seen.add(subcls)
                yield subcls
                yield from walk(subcls)

    return list(walk(cls))


def is_drf_view(cls):
    try:
        from rest_framework.views import APIView
        from rest_framework.viewsets import ViewSetMixin
    except ImportError:
        return False

    return issubclass(cls, (APIView, ViewSetMixin))


def patch_django_views():
    config = get_pg_audit_config()

    try:
        from django.views import View
    except ImportError:
        return

    methods = set(config.get("django_views_methods") or ())

    for cls in get_all_django_views(View, config):
        if not cls or is_drf_view(cls) or not should_patch_django_view(cls, config):
            continue

        attrs = dir(cls)
        for method_name in methods:
            if method_name in attrs:
                decorate_method(cls, method_name, get_django_view_callback)
