from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone

import apps.saved_estimates.models


def populate_validity(apps, schema_editor):
    SavedEstimate = apps.get_model('saved_estimates', 'SavedEstimate')
    for estimate in SavedEstimate.objects.all().iterator():
        local_date = timezone.localtime(estimate.created_at).date()
        valid_from = local_date - timedelta(days=local_date.weekday())
        estimate.valid_from = valid_from
        estimate.valid_until = valid_from + timedelta(days=6)
        estimate.save(update_fields=['valid_from', 'valid_until'])


class Migration(migrations.Migration):

    dependencies = [
        ('saved_estimates', '0002_savedestimate_reference_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='savedestimate',
            name='valid_from',
            field=models.DateField(null=True),
        ),
        migrations.AddField(
            model_name='savedestimate',
            name='valid_until',
            field=models.DateField(null=True),
        ),
        migrations.RunPython(populate_validity, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='savedestimate',
            name='valid_from',
            field=models.DateField(default=apps.saved_estimates.models.current_validity_start),
        ),
        migrations.AlterField(
            model_name='savedestimate',
            name='valid_until',
            field=models.DateField(default=apps.saved_estimates.models.current_validity_end),
        ),
    ]
