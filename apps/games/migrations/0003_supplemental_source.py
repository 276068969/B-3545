from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0002_highlight_featured_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='supplemental_source',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', '正常录入'),
                    ('manual', '手工补录'),
                    ('batch_import', '批量导入'),
                    ('data_restore', '数据恢复'),
                ],
                default='',
                help_text='补录记录的来源类型',
                max_length=20,
                verbose_name='补录来源',
            ),
        ),
    ]
