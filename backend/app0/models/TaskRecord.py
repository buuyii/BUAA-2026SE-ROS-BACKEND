# models.py
from django.db import models
from django.utils import timezone

class TaskRecord(models.Model):
    class Status(models.IntegerChoices):
        RUNNING = 0, '运行中'
        SUCCESS = 1, '成功'
        FAILED = 2, '失败'

    task_index = models.IntegerField(unique=True, help_text="任务索引，来自ROS消息")
    status = models.IntegerField(choices=Status.choices, default=Status.RUNNING)
    message = models.CharField(max_length=100, blank=True, default='')
    result_detail = models.TextField(blank=True, default='')  # 额外信息，如颜色等
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Task {self.task_index} - {self.get_status_display()}"