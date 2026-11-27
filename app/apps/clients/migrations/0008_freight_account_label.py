from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('clients', '0007_one_current_freight_calculator'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='client',
            options={
                'ordering': ['code'],
                'verbose_name': 'Freight Account',
                'verbose_name_plural': 'Freight Accounts',
            },
        ),
    ]
