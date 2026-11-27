from django.db import migrations, models
from django.db.models import Count
from django.utils import timezone


def archive_duplicate_calculators(apps, schema_editor):
    calculator = apps.get_model('clients', 'FreightCalculator')
    calculators = calculator.objects.using(schema_editor.connection.alias)
    duplicates = list(
        calculators.values('client_id').annotate(total=Count('pk'))
        .filter(total__gt=1).values_list('client_id', flat=True)
    )
    archived_at = timezone.now()
    for client_id in duplicates:
        group = calculators.filter(client_id=client_id)
        current = group.order_by('-active', '-updated_at', '-pk').first()
        sth = group.filter(client__code='STH')
        revised = sth.filter(version='V2026.R2').order_by('-active', '-updated_at', '-pk').first()
        if revised is not None:
            current = revised
            previous = sth.filter(version='1.8').order_by('-active', '-updated_at', '-pk').first()
            if previous is not None:
                group.filter(pk=current.pk).update(cubic_margin_options=previous.cubic_margin_options)
        group.exclude(pk=current.pk).update(archived_at=archived_at)


class Migration(migrations.Migration):
    dependencies = [('clients', '0006_client_cubic_dimension_confirmation_factor')]

    operations = [
        migrations.AddField(
            model_name='freightcalculator',
            name='archived_at',
            field=models.DateTimeField(editable=False, null=True),
        ),
        migrations.RunPython(archive_duplicate_calculators),
        migrations.AlterUniqueTogether(name='freightcalculator', unique_together=set()),
        migrations.AddConstraint(
            model_name='freightcalculator',
            constraint=models.UniqueConstraint(
                fields=('client',), condition=models.Q(archived_at__isnull=True),
                name='clients_one_current_freight_calculator',
            ),
        ),
    ]
