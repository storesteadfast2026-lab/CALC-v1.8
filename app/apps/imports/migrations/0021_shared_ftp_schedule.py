import datetime

from django.db import migrations, models


def create_default_schedule(apps, schema_editor):
    FtpImportSchedule = apps.get_model('imports', 'FtpImportSchedule')
    FtpImportSchedule.objects.get_or_create(
        defaults={
            'active': True,
            'run_time': datetime.time(8, 0),
            'monday': True,
            'tuesday': True,
            'wednesday': True,
            'thursday': True,
            'friday': True,
            'saturday': False,
            'sunday': False,
            'retry_minutes': 15,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('imports', '0020_ftpimportconfiguration'),
    ]

    operations = [
        migrations.CreateModel(
            name='FtpImportSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('active', models.BooleanField(default=True)),
                ('run_time', models.TimeField(default=datetime.time(8, 0), help_text='Local Australia/Adelaide time for the shared FTP run.')),
                ('monday', models.BooleanField(default=True)),
                ('tuesday', models.BooleanField(default=True)),
                ('wednesday', models.BooleanField(default=True)),
                ('thursday', models.BooleanField(default=True)),
                ('friday', models.BooleanField(default=True)),
                ('saturday', models.BooleanField(default=False)),
                ('sunday', models.BooleanField(default=False)),
                ('retry_minutes', models.PositiveSmallIntegerField(default=15, help_text='Retry interval for enabled files that were not ready.')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'FTP schedule',
                'verbose_name_plural': 'FTP schedule',
            },
        ),
        migrations.RemoveField(
            model_name='ftpimportconfiguration',
            name='daily_time',
        ),
        migrations.RemoveField(
            model_name='ftpimportconfiguration',
            name='retry_minutes',
        ),
        migrations.RemoveField(
            model_name='ftpimportconfiguration',
            name='run_mode',
        ),
        migrations.RunPython(create_default_schedule, migrations.RunPython.noop),
    ]
