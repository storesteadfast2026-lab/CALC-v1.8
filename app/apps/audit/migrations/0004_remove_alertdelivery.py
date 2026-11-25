from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('audit', '0003_alertdelivery'),
    ]

    operations = [
        migrations.DeleteModel(
            name='AlertDelivery',
        ),
    ]
