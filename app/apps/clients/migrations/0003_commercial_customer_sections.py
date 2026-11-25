from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('clients', '0002_alter_client_options_customer_customerimport')]
    operations = [
        migrations.CreateModel(name='CommercialCustomer', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('code', models.CharField(max_length=40, unique=True)),
            ('name', models.CharField(max_length=150)),
            ('notes', models.TextField(blank=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
        ], options={'ordering': ['code'], 'verbose_name': 'Commercial Customer'}),
        migrations.CreateModel(name='CustomerSection', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('notes', models.TextField(blank=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('commercial_customer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sections', to='clients.commercialcustomer')),
            ('source_customer', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='commercial_section', to='clients.customer')),
        ], options={'ordering': ['source_customer__code'], 'verbose_name': 'Customer Section'}),
    ]
