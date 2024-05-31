def _get_remote_addr(environ: dict):
    return environ.get("HTTP_X_FORWARDED_FOR") or environ.get("REMOTE_ADDR")


def get_ip_addresses(request):
    if isinstance(request, dict):
        return _get_remote_addr(request)

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def get_response_size(response):
    content = getattr(response, "content", None)
    if content is not None and type(content) == bytes:
        return len(response.content)


def get_authenticated_user_by_request(request):
    return request.user if request.user.is_authenticated else None
