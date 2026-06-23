from django.db import models

from django.utils import timezone
from app0.models.Map import Map

class WayPoint(models.Model):
    PICKUP = 0
    DROPOFF = 1

    STATICS_TYPES = [
        (PICKUP, '取货点'),
        (DROPOFF, '放货点'),
    ]

    # 新增货物类型常量
    """  
    0: green_large
    1: green_small
    2: red_large
    3: red_small
    """
    CARGO_A = 0
    CARGO_B = 1
    CARGO_C = 2
    CARGO_D = 3
    CARGO_CHOICES = [
        (CARGO_A, 'green_large'),
        (CARGO_B, 'green_small'),
        (CARGO_C, 'red_large'),
        (CARGO_D, 'red_small')
    ]

    waypoint_id = models.AutoField(primary_key=True)
    map = models.ForeignKey('app0.Map', null=True, blank=True, on_delete=models.CASCADE, related_name='waypoints')
    waypoint_name = models.CharField(max_length=50)
    waypoint_type = models.IntegerField(choices=STATICS_TYPES, default=PICKUP)
    cargo_type = models.IntegerField(
        choices=CARGO_CHOICES,
        null=True,          # 数据库可为NULL
        blank=True,         # Django表单/序列化允许为空
        verbose_name='货物类型'
    )
    px = models.FloatField()
    py = models.FloatField()
    pz = models.FloatField()
    orientation = models.FloatField()
    create_time = create_time = models.DateTimeField(default=timezone.now)