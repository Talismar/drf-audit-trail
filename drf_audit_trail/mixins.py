from django.db import models
from django.utils.translation import gettext_lazy as _


class ProtectedModelMixin:
    def delete(self, using=..., keep_parents=...):
        raise Exception("Deletion of this model is not allowed.")

    def save(
        self,
        *args,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
    ):
        if self.pk is not None:
            raise Exception("Updating of this model is not allowed.")
        super().save(
            *args,
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )


class BaseModelMixin(ProtectedModelMixin, models.Model):
    extra_informations = models.TextField(_("Extra information"), null=True, blank=True)
    datetime = models.DateTimeField(verbose_name=_("Datetime"), auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-datetime"]

    def __str__(self) -> str:
        return "Id: %s" % self.pk
