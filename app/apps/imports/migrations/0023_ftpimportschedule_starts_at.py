from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0022_alter_ftpimportschedule_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='ftpimportschedule',
            name='starts_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
