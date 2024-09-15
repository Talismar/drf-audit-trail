from django import template
from django.contrib.auth import get_user_model

from drf_audit_trail.settings import DRF_AUDIT_TRAIL_USER_PK_NAME

UserModel = get_user_model()


register = template.Library()


@register.filter(name="range")
def make_range(value):
    return range(value)


@register.filter()
def get_item_at_index(list_obj, index):
    try:
        return list_obj[index]
    except IndexError:
        return None


@register.filter(name="get_user_by_id")
def get_user_by_id(user_id):
    try:
        filter_param = {DRF_AUDIT_TRAIL_USER_PK_NAME: user_id}
        user = UserModel.objects.filter(**filter_param).first()
        if user is not None:
            return user
    except ValueError:
        return "-"
