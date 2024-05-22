from django.db import models
from django.utils.translation import gettext_lazy as _


class BaseModelMixin(models.Model):
    extra_informations = models.TextField(_("Extra information"), null=True, blank=True)
    datetime = models.DateTimeField(verbose_name=_("Datetime"), auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-datetime"]

    def __str__(self) -> str:
        return "Id: %s" % self.pk
