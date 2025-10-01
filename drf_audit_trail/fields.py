import logging
from django.db import models

logger = logging.getLogger("drf_audit_trail.truncation")


class TruncatingCharField(models.CharField):
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is not None and self.max_length is not None and len(value) > self.max_length:
            logger.warning(
                f"Truncating value for field '{self.name}' to {self.max_length} characters. Original length: {len(value)}."
            )
            return value[: self.max_length]
        return value
