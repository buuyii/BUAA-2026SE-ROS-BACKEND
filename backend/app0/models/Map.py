from django.db import models

from django.utils import timezone


class Map(models.Model):
    map_id = models.AutoField(primary_key=True)
    map_name = models.CharField(max_length=50)
    map_file_path = models.CharField(max_length=200)
    annotation_file_path = models.CharField(max_length=200)
    create_time = models.DateTimeField(default=timezone.now)
    update_time = models.DateTimeField(default=timezone.now)