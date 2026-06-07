from django.contrib.auth.models import AbstractUser
from django.db import models
import os


def avatar_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    return f'avatars/user_{instance.pk}.{ext}'


class User(AbstractUser):
    nickname = models.CharField('昵称', max_length=50, blank=True)
    avatar = models.ImageField('头像', upload_to=avatar_upload_path, blank=True, null=True)
    bio = models.TextField('个人简介', max_length=200, blank=True)
    created_at = models.DateTimeField('注册时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = '用户列表'

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self):
        return self.nickname or self.username

    def get_avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return '/static/img/default_avatar.png'

    @property
    def stats(self):
        from apps.games.models import PlayerStats
        stats, _ = PlayerStats.objects.get_or_create(user=self)
        return stats
