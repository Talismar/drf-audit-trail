from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


class Test(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)


# @receiver(pre_save, sender=Test)
# def test_pre_save(sender, instance, created, **kwargs):
#     if not created:
#         old_instance = sender.objects.get(pk=instance.pk)
#         # delta = model_delta(old_model, instance)
#     print(sender, instance, kwargs)


# # @receiver(post_save, sender=Test)
# def test_post_save(sender, instance, created, **kwargs):
#     print(sender, instance, created, kwargs)


# post_save.connect(test_post_save, dispatch_uid="drf_audit_trail_post_save")
# pre_save.connect(test_pre_save, dispatch_uid="drf_audit_trail_pre_save")
