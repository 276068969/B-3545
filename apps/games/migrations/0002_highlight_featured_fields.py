from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('games', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='highlight',
            name='featured_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='精选时间'),
        ),
        migrations.AddField(
            model_name='highlight',
            name='featured_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='featured_highlights',
                to=settings.AUTH_USER_MODEL,
                verbose_name='精选操作人',
            ),
        ),
        migrations.AddField(
            model_name='highlight',
            name='featured_note',
            field=models.TextField(blank=True, help_text='管理员补充的精选说明文字', verbose_name='精选说明'),
        ),
        migrations.AddField(
            model_name='highlight',
            name='featured_title',
            field=models.CharField(
                blank=True,
                help_text='管理员自定义的精选标题，留空则使用原标题',
                max_length=100,
                verbose_name='精选标题',
            ),
        ),
        migrations.AddField(
            model_name='highlight',
            name='is_pinned',
            field=models.BooleanField(default=False, help_text='置顶的高光会排在最前面', verbose_name='置顶'),
        ),
        migrations.AlterModelOptions(
            name='highlight',
            options={
                'ordering': ['-is_pinned', '-is_featured', '-highlight_score', '-created_at'],
                'verbose_name': '高光时刻',
                'verbose_name_plural': '高光时刻列表',
            },
        ),
    ]
