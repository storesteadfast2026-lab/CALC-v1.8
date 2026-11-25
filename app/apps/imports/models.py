from datetime import time
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.clients.models import Client


def product_master_upload_to(instance, filename):
    """Store each global workbook snapshot independently of any Client."""
    from uuid import uuid4
    return f'product_master/{timezone.localdate():%Y/%m}/{uuid4().hex}_{Path(filename).name}'


class ProductMaster(models.Model):
    """Company-wide Product source snapshot; never owned by a Client."""

    STATUS_CHOICES = [
        ('UPLOADED', 'Uploaded'),
        ('VALIDATED', 'Validated'),
        ('VALIDATION_FAILED', 'Validation failed'),
    ]
    original_file = models.FileField(upload_to=product_master_upload_to)
    original_filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, db_index=True)
    file_size_bytes = models.PositiveBigIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='product_masters_uploaded',
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='UPLOADED')
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='product_masters_validated',
    )
    validation_summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Product Master'
        verbose_name_plural = 'Product Masters'

    def __str__(self):
        return f'{self.original_filename} ({self.pk})'


def stock_master_upload_to(instance, filename):
    """Store each global Stock snapshot independently of any Client."""
    from uuid import uuid4
    return f'stock_master/{timezone.localdate():%Y/%m}/{uuid4().hex}_{Path(filename).name}'


class StockMaster(models.Model):
    """Company-wide Stock source snapshot used only for read-only comparison."""

    STATUS_CHOICES = [
        ('UPLOADED', 'Uploaded'),
        ('VALIDATED', 'Validated'),
        ('VALIDATION_FAILED', 'Validation failed'),
    ]
    original_file = models.FileField(upload_to=stock_master_upload_to)
    original_filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, db_index=True)
    file_size_bytes = models.PositiveBigIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='stock_masters_uploaded',
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='UPLOADED')
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_masters_validated',
    )
    validation_summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Stock Master'
        verbose_name_plural = 'Stock Masters'

    def __str__(self):
        return f'{self.original_filename} ({self.pk})'


class GlobalStockSourceRow(models.Model):
    """Immutable valid detail row from a global Stock Master snapshot."""

    stock_master = models.ForeignKey(
        StockMaster,
        on_delete=models.CASCADE,
        related_name='source_rows',
    )
    source_row_number = models.PositiveIntegerField()
    customer_code = models.CharField(max_length=100, blank=True, default='', db_index=True)
    product_code_raw = models.CharField(max_length=255)
    product_code_normalized = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    category = models.CharField(max_length=255, blank=True)
    serial_no = models.CharField(max_length=255, blank=True)
    cubic = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    weight = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['source_row_number']
        constraints = [
            models.UniqueConstraint(
                fields=['stock_master', 'source_row_number'],
                name='imports_global_stock_master_row_uniq',
            ),
        ]
        indexes = [
            models.Index(
                fields=['stock_master', 'customer_code', 'product_code_normalized'],
                name='imp_gstock_cust_sku_idx',
            ),
        ]

    def __str__(self):
        return f'{self.stock_master_id}:{self.source_row_number} {self.product_code_normalized}'


def external_data_upload_to(instance, filename):
    """Build a stable, versioned path for uploaded/downloaded source files."""
    timestamp = timezone.localtime().strftime('%Y%m%d_%H%M%S')
    safe_name = Path(filename).name.replace(' ', '_')
    client_code = getattr(instance.client, 'code', 'unknown').lower()
    file_type = (instance.file_type or 'other').lower()
    return f'external_imports/{client_code}/{file_type}/{timezone.localdate():%Y/%m}/{timestamp}_{safe_name}'


class ExternalDataFile(models.Model):
    """Uploaded or downloaded external source with validation/import history."""

    FILE_TYPES = [
        ('PRODUCTS', 'Products'),
        ('STOCK', 'Stock'),
        ('FUEL', 'Fuel'),
        ('ZONES', 'Zones'),
        ('RATES', 'Rates'),
        ('SUBURBS', 'Suburbs'),
        ('WORKBOOK', 'Full Excel Workbook'),
    ]
    SOURCE_METHODS = [
        ('ADMIN_UPLOAD', 'Admin upload'),
        ('ADMIN_WEB_FETCH', 'Admin web fetch'),
        ('FTP_DROP', 'FTP uploaded_data drop'),
        ('COMMAND', 'Management command'),
    ]
    STATUSES = [
        ('UPLOADED', 'Uploaded'),
        ('DOWNLOADED', 'Downloaded'),
        ('VALIDATED', 'Validated'),
        ('VALIDATION_FAILED', 'Validation failed'),
        ('ACTIVE', 'Active'),
        ('IMPORT_FAILED', 'Import failed'),
        ('ROLLED_BACK', 'Rolled back'),
        ('IMPORTED', 'Imported'),
        ('ERROR', 'Error'),
        ('ARCHIVED', 'Archived'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='external_files')
    file_type = models.CharField(max_length=30, choices=FILE_TYPES)
    source_method = models.CharField(max_length=30, choices=SOURCE_METHODS, default='ADMIN_UPLOAD')
    source_url = models.URLField(max_length=1000, blank=True)
    original_filename = models.CharField(max_length=255)
    uploaded_file = models.FileField(upload_to=external_data_upload_to, null=True, blank=True)
    # Kept for backwards compatibility with command-created workbook records.
    stored_path = models.CharField(max_length=500, blank=True, default='')
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    mime_type = models.CharField(max_length=120, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    notes = models.TextField(blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='external_files_uploaded',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, choices=STATUSES, default='UPLOADED', db_index=True)

    validation_summary = models.JSONField(default=dict, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='external_files_validated',
    )
    validated_at = models.DateTimeField(null=True, blank=True)

    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='external_files_imported',
    )
    last_imported_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='external_files_activated',
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    rolled_back_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='external_files_rolled_back',
    )
    rolled_back_at = models.DateTimeField(null=True, blank=True)
    previous_active_file = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replacement_files',
    )

    import_summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']
        permissions = [
            ('validate_external_data_file', 'Can validate external data files'),
            ('activate_fuel', 'Can activate fuel rates'),
            ('rollback_fuel', 'Can rollback fuel rates'),
            ('load_rate_sources', 'Can load and roll back rate and zone source versions'),
            ('download_external_data_file', 'Can download external data files'),
        ]

    def __str__(self):
        return f'{self.client.code} {self.file_type} {self.original_filename}'

    @property
    def local_path(self):
        if self.uploaded_file:
            try:
                return self.uploaded_file.path
            except (NotImplementedError, ValueError):
                return ''
        return self.stored_path


class FtpImportSchedule(models.Model):
    """One shared Adelaide schedule for all enabled FTP file mappings."""

    WEEKDAY_FIELDS = (
        'monday', 'tuesday', 'wednesday', 'thursday',
        'friday', 'saturday', 'sunday',
    )

    active = models.BooleanField(default=True)
    run_time = models.TimeField(
        default=time(8, 0),
        help_text='Local Australia/Adelaide time for the shared FTP run.',
    )
    monday = models.BooleanField(default=True)
    tuesday = models.BooleanField(default=True)
    wednesday = models.BooleanField(default=True)
    thursday = models.BooleanField(default=True)
    friday = models.BooleanField(default=True)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    retry_minutes = models.PositiveSmallIntegerField(
        default=15,
        help_text='Retry interval for enabled files that were not ready.',
    )
    starts_at = models.DateTimeField(null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Import Centre'
        verbose_name_plural = 'Import Centre'

    def __str__(self):
        return f'FTP schedule at {self.run_time}'

    def clean(self):
        super().clean()
        if FtpImportSchedule.objects.exclude(pk=self.pk).exists():
            raise ValidationError('Only one shared FTP schedule is allowed.')
        if not 1 <= self.retry_minutes <= 1440:
            raise ValidationError({
                'retry_minutes': 'Retry interval must be between 1 and 1440 minutes.',
            })
        if not any(getattr(self, day) for day in self.WEEKDAY_FIELDS):
            raise ValidationError('Select at least one day of the week.')


class FtpImportConfiguration(models.Model):
    """One enabled client/file mapping processed by the shared FTP schedule."""
    RESULT_STATUSES = [
        ('NEVER', 'Never checked'),
        ('NEW_SNAPSHOT', 'New snapshot registered'),
        ('UNCHANGED', 'File unchanged'),
        ('WAITING', 'Waiting for a complete file'),
        ('ERROR', 'Error'),
    ]

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='ftp_import_configurations',
    )
    file_type = models.CharField(max_length=30, choices=ExternalDataFile.FILE_TYPES)
    filename = models.CharField(
        max_length=255,
        help_text='Simple filename located directly inside uploaded_data, for example products.xls.',
    )
    minimum_file_age_seconds = models.PositiveIntegerField(
        default=60,
        help_text='Wait this long after the source file was last modified before reading it.',
    )
    active = models.BooleanField(default=True)

    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=20,
        choices=RESULT_STATUSES,
        default='NEVER',
    )
    last_message = models.TextField(blank=True)
    last_snapshot = models.ForeignKey(
        ExternalDataFile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ftp_configuration_results',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['client__code', 'filename']
        verbose_name = 'FTP import configuration'
        verbose_name_plural = 'FTP import configurations'
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'filename'],
                name='imports_ftp_config_client_filename_uniq',
            ),
        ]
        permissions = [
            ('run_ftp_import_configuration', 'Can run FTP import configurations'),
        ]

    def __str__(self):
        return f'{self.client.code} / {self.filename}'

    def clean(self):
        super().clean()
        raw_name = str(self.filename or '').strip()
        if not raw_name or Path(raw_name).name != raw_name or raw_name in {'.', '..'}:
            raise ValidationError({
                'filename': 'Use a simple filename directly inside uploaded_data; folders are not allowed.',
            })
        self.filename = raw_name
        if self.minimum_file_age_seconds > 86400:
            raise ValidationError({
                'minimum_file_age_seconds': 'The maximum file age wait is 86400 seconds.',
            })


class ProductSourceRow(models.Model):
    """Read-only valid staging row loaded from a Product source file."""

    external_file = models.ForeignKey(
        ExternalDataFile,
        on_delete=models.CASCADE,
        related_name='product_source_rows',
        limit_choices_to={'file_type': 'PRODUCTS'},
    )
    source_row_number = models.PositiveIntegerField()
    customer_code = models.CharField(max_length=100, blank=True, default='', db_index=True)
    product_code_raw = models.CharField(max_length=255)
    product_code_normalized = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=255, blank=True)
    length_mm = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    width_mm = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    height_mm = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    cubic_m3 = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    pallet = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    comment = models.TextField(blank=True)
    source_status = models.CharField(max_length=100, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['source_row_number']
        constraints = [
            models.UniqueConstraint(
                fields=['external_file', 'source_row_number'],
                name='imports_product_source_file_row_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['external_file', 'product_code_normalized'], name='imp_prod_file_sku_idx'),
            models.Index(fields=['external_file', 'customer_code', 'product_code_normalized'], name='imp_prod_file_cust_sku_idx'),
        ]

    def __str__(self):
        return f'{self.external_file_id}:{self.source_row_number} {self.product_code_normalized}'


class ProductSourceRejectedRow(models.Model):
    """Product source row isolated because it cannot be mapped safely."""

    REPAIR_STATUSES = [
        ('PENDING', 'Pending review'),
        ('PROPOSED', 'Proposal saved'),
        ('APPROVED', 'Approved into staging'),
    ]

    external_file = models.ForeignKey(
        ExternalDataFile,
        on_delete=models.CASCADE,
        related_name='product_rejected_rows',
        limit_choices_to={'file_type': 'PRODUCTS'},
    )
    source_row_number = models.PositiveIntegerField()
    customer_code = models.CharField(max_length=100, blank=True, default='', db_index=True)
    column_count = models.PositiveIntegerField(null=True, blank=True)
    raw_values = models.JSONField(default=list, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    repair_status = models.CharField(
        max_length=20,
        choices=REPAIR_STATUSES,
        default='PENDING',
        db_index=True,
    )
    proposed_data = models.JSONField(default=dict, blank=True)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_product_source_rejections',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    staged_row = models.OneToOneField(
        ProductSourceRow,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_repair',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['source_row_number']
        constraints = [
            models.UniqueConstraint(
                fields=['external_file', 'source_row_number'],
                name='imports_product_rejected_file_row_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.external_file_id}:{self.source_row_number} rejected'


class ProductReconciliationDecision(models.Model):
    """Draft field-level decision for one Product reconciliation row."""

    DECISION_STATUSES = [
        ('DRAFT', 'Draft'),
        ('READY', 'Ready for preview'),
        ('APPLIED', 'Applied'),
    ]
    ROW_ACTIONS = [
        ('UPDATE', 'Update operational Product'),
        ('DELETE', 'Remove operational Product'),
    ]

    external_file = models.ForeignKey(
        ExternalDataFile,
        on_delete=models.CASCADE,
        related_name='product_reconciliation_decisions',
        limit_choices_to={'file_type': 'PRODUCTS'},
    )
    product_code_normalized = models.CharField(max_length=400, db_index=True)
    source_row_number = models.PositiveIntegerField(null=True, blank=True)
    row_status = models.CharField(max_length=30)
    group_key = models.CharField(max_length=80, db_index=True)
    field_decisions = models.JSONField(default=dict)
    custom_values = models.JSONField(default=dict, blank=True)
    row_action = models.CharField(
        max_length=12,
        choices=ROW_ACTIONS,
        default='UPDATE',
    )
    decision_status = models.CharField(
        max_length=20,
        choices=DECISION_STATUSES,
        default='DRAFT',
        db_index=True,
    )
    notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='product_reconciliation_decisions',
    )
    reviewed_at = models.DateTimeField(auto_now=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='applied_product_reconciliation_decisions',
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    apply_batch_id = models.CharField(max_length=32, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['external_file', 'product_code_normalized']
        constraints = [
            models.UniqueConstraint(
                fields=['external_file', 'product_code_normalized'],
                name='imp_prod_recon_file_sku_uniq',
            ),
        ]
        permissions = [
            ('manage_product_reconciliation', 'Can manage Product reconciliation drafts'),
        ]

    def __str__(self):
        return f'{self.external_file_id}:{self.product_code_normalized} {self.decision_status}'


class ProductCorrectionRound(models.Model):
    """A later, independent set of decisions against the same immutable source."""

    external_file = models.ForeignKey(
        ExternalDataFile, on_delete=models.PROTECT, related_name='product_correction_rounds'
    )
    status = models.CharField(max_length=16, default='DRAFT')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    apply_batch_id = models.CharField(max_length=32, blank=True)


class ProductCorrectionDecision(models.Model):
    """Retained per-round decision; prior applied decisions remain untouched."""

    round = models.ForeignKey(
        ProductCorrectionRound, on_delete=models.PROTECT, related_name='decisions'
    )
    sku = models.CharField(max_length=400)
    field_decisions = models.JSONField(default=dict)
    custom_values = models.JSONField(default=dict, blank=True)
    notes = models.TextField()
    confirm_source_dimensions = models.BooleanField(default=False)
    source_fingerprint = models.CharField(max_length=64)
    before_values = models.JSONField(default=dict)
    after_values = models.JSONField(default=dict, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(auto_now=True)

    @property
    def row_action(self):
        return 'UPDATE'

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['round', 'sku'], name='imp_product_corr_round_sku_uniq'),
        ]


class ProductReconciliationRule(models.Model):
    """Reusable group-level proposal for future Product source files."""

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='product_reconciliation_rules',
    )
    name = models.CharField(max_length=160)
    group_key = models.CharField(max_length=80, db_index=True)
    field_decisions = models.JSONField(default=dict)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_product_reconciliation_rules',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['client', 'group_key', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'name'],
                name='imp_prod_recon_rule_client_name_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.client.code}:{self.name}'


class ExternalDataCorrectionMemory(models.Model):
    """Reusable, audited correction approved for an external-data workflow."""

    workflow_key = models.CharField(max_length=80, db_index=True)
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='external_data_correction_memories',
    )
    record_key = models.CharField(max_length=400, blank=True, db_index=True)
    source_fingerprint = models.CharField(max_length=64, db_index=True)
    proposal_fingerprint = models.CharField(max_length=64, db_index=True)
    source_data = models.JSONField(default=dict, blank=True)
    approved_data = models.JSONField(default=dict, blank=True)
    approval_note = models.TextField(blank=True)
    origin_external_file = models.ForeignKey(
        ExternalDataFile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='originated_correction_memories',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_external_data_corrections',
    )
    approved_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    use_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['workflow_key', 'record_key', '-approved_at']
        constraints = [
            models.UniqueConstraint(
                fields=['workflow_key', 'client', 'source_fingerprint'],
                name='imp_corrmem_source_uniq',
            ),
        ]
        indexes = [
            models.Index(
                fields=['workflow_key', 'client', 'record_key', 'is_active'],
                name='imp_corrmem_lookup_idx',
            ),
        ]

    def __str__(self):
        return f'{self.workflow_key}:{self.client_id}:{self.record_key}'


class StockSourceRow(models.Model):
    """Read-only staging row loaded from stock_sth.xlsx."""

    external_file = models.ForeignKey(
        ExternalDataFile,
        on_delete=models.CASCADE,
        related_name='stock_source_rows',
        limit_choices_to={'file_type': 'STOCK'},
    )
    source_row_number = models.PositiveIntegerField()
    movement_number = models.CharField(max_length=100, blank=True)
    stock_date_raw = models.CharField(max_length=100, blank=True)
    customer = models.CharField(max_length=100, blank=True)
    product_code_raw = models.CharField(max_length=255)
    product_code_normalized = models.CharField(max_length=255, db_index=True)
    sql_name = models.CharField(max_length=500, blank=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    pallet = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    group1 = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    stock_class = models.CharField(max_length=255, blank=True)
    sql_stock_ref = models.CharField(max_length=255, blank=True)
    weight_kg = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    cubic_m3 = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    depot = models.CharField(max_length=255, blank=True)
    sql_group = models.CharField(max_length=255, blank=True)
    sql_group1 = models.CharField(max_length=255, blank=True)
    expiry_raw = models.CharField(max_length=100, blank=True)
    pallet_ref = models.CharField(max_length=255, blank=True)
    serial_no = models.CharField(max_length=255, blank=True)
    source_status = models.CharField(max_length=100, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['source_row_number']
        constraints = [
            models.UniqueConstraint(
                fields=['external_file', 'source_row_number'],
                name='imports_stock_source_file_row_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['external_file', 'product_code_normalized'], name='imp_stock_file_sku_idx'),
        ]

    def __str__(self):
        return f'{self.external_file_id}:{self.source_row_number} {self.product_code_normalized}'


class ExternalDataReviewItem(models.Model):
    """Generic review decision linked to one external source row."""

    external_file = models.ForeignKey(
        ExternalDataFile,
        on_delete=models.CASCADE,
        related_name='external_data_review_items',
    )
    row_key = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=50, blank=True)
    source_data = models.JSONField(default=dict, blank=True)
    current_data = models.JSONField(default=dict, blank=True)
    diagnostic_data = models.JSONField(default=dict, blank=True)
    proposed_action = models.CharField(max_length=50, blank=True)
    decision = models.CharField(max_length=50, default='PENDING')
    notes = models.TextField(blank=True)
    corrected_suburb = models.CharField(max_length=120, blank=True)
    corrected_state = models.CharField(max_length=10, blank=True)
    corrected_postcode = models.CharField(max_length=10, blank=True)
    selected_historical_suburb_id = models.BigIntegerField(null=True, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='external_data_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_result = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['external_file', 'row_key']
        constraints = [
            models.UniqueConstraint(
                fields=['external_file', 'row_key'],
                name='imports_review_file_row_uniq',
            ),
        ]
        indexes = [
            models.Index(
                fields=['external_file', 'decision', 'is_current'],
                name='imp_review_file_dec_idx',
            ),
        ]

    def __str__(self):
        return f'{self.external_file_id}:{self.row_key} {self.decision}'


class ImportReconciliationException(models.Model):
    """Durable review record; does not represent an operational Product."""
    STATUS_CHOICES = [
        ('OPEN', 'Open'), ('UNDER_REVIEW', 'Under review'),
        ('ACCEPTED_EXCEPTION', 'Accepted exception'), ('RESOLVED', 'Resolved'),
    ]
    KIND_CHOICES = [
        ('MISSING_PRODUCT', 'Missing Product in source Section'),
        ('CROSS_SECTION_CANDIDATE', 'Cross-section candidate'),
        ('UNKNOWN_CUSTOMER', 'Unknown source Customer'),
        ('AMBIGUOUS_PRODUCT', 'Ambiguous source Product'),
        ('INVALID_IDENTIFIER', 'Invalid identifier'),
    ]
    source_stock_sha256 = models.CharField(max_length=64, db_index=True)
    source_product_sha256 = models.CharField(max_length=64)
    section_code = models.CharField(max_length=100, db_index=True)
    sku = models.CharField(max_length=255)
    kind = models.CharField(max_length=40, choices=KIND_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='OPEN')
    stock_row_count = models.PositiveIntegerField(default=0)
    evidence = models.JSONField(default=dict, blank=True)
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='reviewed_import_exceptions')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(
            fields=['source_stock_sha256', 'source_product_sha256', 'section_code', 'sku', 'kind'],
            name='imp_except_source_section_sku_kind_uq')]

    def __str__(self):
        return f'{self.section_code} / {self.sku} — {self.kind}'


class RateCardLine(models.Model):
    """One rates_all.xls row in a stored version; activated STH quotes read it."""

    external_file = models.ForeignKey(
        ExternalDataFile,
        on_delete=models.CASCADE,
        related_name='rate_card_lines',
        limit_choices_to={'file_type': 'RATES'},
    )
    source_row = models.PositiveIntegerField()
    master_rate = models.PositiveIntegerField()
    rate_no = models.CharField(max_length=30)
    break_no = models.IntegerField(default=0)
    item_no = models.IntegerField(default=0)
    code = models.CharField(max_length=60, blank=True)
    run_rate = models.PositiveIntegerField(null=True, blank=True)
    name = models.CharField(max_length=255, blank=True)
    filter_field = models.TextField(blank=True)
    from_value = models.CharField(max_length=255, blank=True)
    greater = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    upto = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    to_value = models.CharField(max_length=255, blank=True)
    band = models.CharField(max_length=60, blank=True)
    each = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    unit = models.CharField(max_length=30, blank=True)
    rate = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    basic_charge = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    min_charge = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    cubic = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    gl_code = models.CharField(max_length=60, blank=True)
    analysis = models.CharField(max_length=60, blank=True)
    gst_code = models.CharField(max_length=30, blank=True)
    rcst = models.CharField(max_length=10, blank=True)
    rc_name = models.CharField(max_length=255, blank=True)
    rtst = models.CharField(max_length=10, blank=True)
    group1 = models.CharField(max_length=60, blank=True)
    rate_code = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ['master_rate', 'break_no', 'item_no', 'source_row']
        constraints = [
            models.UniqueConstraint(fields=['external_file', 'source_row'], name='unique_rate_card_source_row'),
        ]
        indexes = [models.Index(fields=['external_file', 'master_rate'], name='rate_card_line_file_card')]

    def __str__(self):
        return f'{self.master_rate} {self.break_no}/{self.item_no} {self.name}'


class ZoneSourceRow(models.Model):
    """One zones.csv row in a stored version; activated STH quotes read it."""

    external_file = models.ForeignKey(
        ExternalDataFile,
        on_delete=models.CASCADE,
        related_name='zone_source_rows',
        limit_choices_to={'file_type': 'ZONES'},
    )
    source_row = models.PositiveIntegerField()
    carrier = models.CharField(max_length=60)
    suburb = models.CharField(max_length=120)
    state = models.CharField(max_length=10)
    postcode = models.CharField(max_length=10, blank=True)
    zone = models.CharField(max_length=40, blank=True)
    subzone = models.CharField(max_length=40, blank=True)
    area = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ['carrier', 'suburb', 'state', 'source_row']
        constraints = [
            models.UniqueConstraint(fields=['external_file', 'source_row'], name='unique_zone_source_row'),
        ]
        indexes = [models.Index(fields=['external_file', 'carrier', 'suburb', 'state'], name='zone_source_lookup')]

    def __str__(self):
        return f'{self.carrier} {self.suburb}, {self.state} -> {self.zone}'
