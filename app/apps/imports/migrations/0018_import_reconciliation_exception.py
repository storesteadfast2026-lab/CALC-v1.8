from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('imports', '0017_global_stock_master_phase1'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.CreateModel(name='ImportReconciliationException', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('source_stock_sha256', models.CharField(db_index=True, max_length=64)),
        ('source_product_sha256', models.CharField(max_length=64)),
        ('section_code', models.CharField(db_index=True, max_length=100)),
        ('sku', models.CharField(max_length=255)),
        ('kind', models.CharField(choices=[('MISSING_PRODUCT', 'Missing Product in source Section'), ('CROSS_SECTION_CANDIDATE', 'Cross-section candidate'), ('UNKNOWN_CUSTOMER', 'Unknown source Customer'), ('AMBIGUOUS_PRODUCT', 'Ambiguous source Product'), ('INVALID_IDENTIFIER', 'Invalid identifier')], max_length=40)),
        ('status', models.CharField(choices=[('OPEN', 'Open'), ('UNDER_REVIEW', 'Under review'), ('ACCEPTED_EXCEPTION', 'Accepted exception'), ('RESOLVED', 'Resolved')], default='OPEN', max_length=30)),
        ('stock_row_count', models.PositiveIntegerField(default=0)),
        ('evidence', models.JSONField(blank=True, default=dict)),
        ('review_notes', models.TextField(blank=True)),
        ('reviewed_at', models.DateTimeField(blank=True, null=True)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('updated_at', models.DateTimeField(auto_now=True)),
        ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_import_exceptions', to=settings.AUTH_USER_MODEL)),
    ], options={'ordering': ['-created_at']}) ,
    migrations.AddConstraint(model_name='importreconciliationexception', constraint=models.UniqueConstraint(fields=('source_stock_sha256', 'source_product_sha256', 'section_code', 'sku', 'kind'), name='imp_except_source_section_sku_kind_uq')),
    ]
