import datetime

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0006_client_cubic_dimension_confirmation_factor'),
        ('imports', '0019_rate_source_rows'),
    ]

    operations = [
        migrations.CreateModel(
            name='FtpImportConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file_type', models.CharField(choices=[('PRODUCTS', 'Products'), ('STOCK', 'Stock'), ('FUEL', 'Fuel'), ('ZONES', 'Zones'), ('RATES', 'Rates'), ('SUBURBS', 'Suburbs'), ('WORKBOOK', 'Full Excel Workbook')], max_length=30)),
                ('filename', models.CharField(help_text='Simple filename located directly inside uploaded_data, for example products.xls.', max_length=255)),
                ('run_mode', models.CharField(choices=[('MANUAL', 'Manual only'), ('AUTOMATIC', 'Automatic daily')], default='MANUAL', max_length=20)),
                ('daily_time', models.TimeField(default=datetime.time(2, 0), help_text='Local Australia/Adelaide time used by Automatic daily mode.')),
                ('minimum_file_age_seconds', models.PositiveIntegerField(default=60, help_text='Wait this long after the source file was last modified before reading it.')),
                ('retry_minutes', models.PositiveSmallIntegerField(default=15, help_text="Retry interval when today's automatic check cannot register the file.")),
                ('active', models.BooleanField(default=True)),
                ('last_checked_at', models.DateTimeField(blank=True, null=True)),
                ('last_success_at', models.DateTimeField(blank=True, null=True)),
                ('last_status', models.CharField(choices=[('NEVER', 'Never checked'), ('NEW_SNAPSHOT', 'New snapshot registered'), ('UNCHANGED', 'File unchanged'), ('WAITING', 'Waiting for a complete file'), ('ERROR', 'Error')], default='NEVER', max_length=20)),
                ('last_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ftp_import_configurations', to='clients.client')),
                ('last_snapshot', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ftp_configuration_results', to='imports.externaldatafile')),
            ],
            options={
                'verbose_name': 'FTP import configuration',
                'verbose_name_plural': 'FTP import configurations',
                'ordering': ['client__code', 'filename'],
                'permissions': [('run_ftp_import_configuration', 'Can run FTP import configurations')],
            },
        ),
        migrations.AddConstraint(
            model_name='ftpimportconfiguration',
            constraint=models.UniqueConstraint(fields=('client', 'filename'), name='imports_ftp_config_client_filename_uniq'),
        ),
    ]
