def get_global_audit_extra_informations(
    *,
    instance,
    model,
    action,
    request=None,
    field_name=None,
    old_raw_value=None,
    new_raw_value=None,
    **kwargs,
):
    data = {
        "app_label": model._meta.app_label,
        "model": model._meta.model_name,
        "model_label": model._meta.label_lower,
        "object_id": instance.pk,
        "action": action,
    }

    if field_name is not None:
        data["field_name"] = field_name
    if old_raw_value is not None:
        data["old_raw_value"] = old_raw_value
    if new_raw_value is not None:
        data["new_raw_value"] = new_raw_value

    if request is None:
        data["source"] = "system"
        return data

    data.update(
        {
            "source": "request",
            "request_method": request.method,
            "request_path": request.path,
        }
    )
    return data
