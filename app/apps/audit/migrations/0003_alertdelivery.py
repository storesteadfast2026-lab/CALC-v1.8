from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0002_fuel_audit_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='AlertDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('channel', models.CharField(choices=[('TEAMS_WORKFLOW', 'Microsoft Teams Workflow')], default='TEAMS_WORKFLOW', max_length=30)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('SENT', 'Sent'), ('FAILED', 'Failed')], default='PENDING', max_length=12)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('response_code', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('error_message', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alert_deliveries', to='audit.auditevent')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='alertdelivery',
            constraint=models.UniqueConstraint(fields=('event', 'channel'), name='audit_unique_event_alert_channel'),
        ),
    ]
