from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('imports', '0021_shared_ftp_schedule'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='ftpimportschedule',
            options={
                'verbose_name': 'Import Centre',
                'verbose_name_plural': 'Import Centre',
            },
        ),
    ]
