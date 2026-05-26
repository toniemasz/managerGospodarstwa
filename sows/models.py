from django.db import models

from django.db import models


class SowModel(models.Model):
    sow_id = models.CharField(max_length=50, unique=True, primary_key=True)
    ear_tag = models.CharField(max_length=50)
    birth_date = models.DateField()

    def __str__(self):
        return f"Maciora {self.ear_tag}"


class SowEventModel(models.Model):
    EVENT_TYPES = [
        ('INSEMINATION', 'Inseminacja'),
        ('FARROWING', 'Oproszenie'),
        ('WEANING', 'Odsadzenie'),
    ]

    sow = models.ForeignKey(SowModel, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    event_date = models.DateField()
    details = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.event_type} - {self.event_date} (Maciora: {self.sow.ear_tag})"
