from django.db import migrations, models


def configure_sth_outer(apps, schema_editor):
    Client = apps.get_model('clients', 'Client')
    Client.objects.filter(code__iexact='STH').update(dimension_fallback_source='OUTER')


def reset_sth_fallback(apps, schema_editor):
    Client = apps.get_model('clients', 'Client')
    Client.objects.filter(
        code__iexact='STH', dimension_fallback_source='OUTER',
    ).update(dimension_fallback_source='NONE')


class Migration(migrations.Migration):
    dependencies = [('clients', '0004_calculator_business_options')]

    operations = [
        migrations.AddField(
            model_name='client',
            name='dimension_fallback_source',
            field=models.CharField(
                choices=[
                    ('NONE', 'No fallback'),
                    ('OUTER', 'Outer dimensions'),
                    ('INNER', 'Inner dimensions'),
                    ('PIECE', 'Piece dimensions'),
                ],
                default='NONE',
                help_text=(
                    'Used only when all three primary Product dimensions are zero or missing. '
                    'Primary dimensions always take precedence.'
                ),
                max_length=10,
            ),
        ),
        migrations.RunPython(configure_sth_outer, reset_sth_fallback),
    ]
