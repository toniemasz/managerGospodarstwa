from django.conf import settings
from django.db import models


class FarmModel(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='farm')
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gospodarstwo"
        verbose_name_plural = "Gospodarstwa"

    def __str__(self):
        return self.name
