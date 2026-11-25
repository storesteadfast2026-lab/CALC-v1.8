from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Client(models.Model):
    """Customer account that owns a calculator."""
    DIMENSION_FALLBACK_CHOICES = [
        ('NONE', 'No fallback'),
        ('OUTER', 'Outer dimensions'),
        ('INNER', 'Inner dimensions'),
        ('PIECE', 'Piece dimensions'),
    ]

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    dimension_fallback_source = models.CharField(
        max_length=10,
        choices=DIMENSION_FALLBACK_CHOICES,
        default='NONE',
        help_text=(
            'Used only when all three primary Product dimensions are zero or missing. '
            'Primary dimensions always take precedence.'
        ),
    )
    cubic_dimension_confirmation_factor = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=Decimal('10'),
        validators=[MinValueValidator(Decimal('1.001'))],
        help_text=(
            'Require Contact Center or Customer Service confirmation when the recorded '
            'cubic volume differs from length × width × height by this factor or more.'
        ),
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Calculator Customer'
        verbose_name_plural = 'Calculator Customers'

    def __str__(self):
        return f'{self.code} - {self.name}'


class FreightCalculator(models.Model):
    """Calculator configuration for each client."""
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='calculators')
    name = models.CharField(max_length=150)
    version = models.CharField(max_length=80, blank=True)
    calculation_engine_key = models.CharField(max_length=80, default='sth_v2026_r2')
    custom_freight_enabled = models.BooleanField(default=True)
    cubic_margin_enabled = models.BooleanField(default=True)
    cubic_margin_options = models.JSONField(default=list, blank=True)
    visible_history_days = models.PositiveSmallIntegerField(default=14)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('client', 'name', 'version')]

    def __str__(self):
        return f'{self.client.code} / {self.name} {self.version}'

    def allowed_cubic_margins(self):
        """Return configured whole-number allowances, always including zero."""
        values = {0}
        for raw_value in self.cubic_margin_options or []:
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 100:
                values.add(value)
        return sorted(values)


class Customer(models.Model):
    """Translogic customer master; independent of Calculator Customers."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    group = models.CharField(max_length=40, blank=True)
    group1 = models.CharField(max_length=40, blank=True)
    group2 = models.CharField(max_length=40, blank=True)
    their_code = models.CharField(max_length=40, blank=True)
    wh_pick_code = models.CharField(max_length=40, blank=True)
    acn = models.CharField(max_length=40, blank=True)
    abn = models.CharField(max_length=40, blank=True)
    gst_code = models.CharField(max_length=40, blank=True)
    sett_days = models.PositiveSmallIntegerField(null=True, blank=True)
    paydays_type = models.CharField(max_length=40, blank=True)
    source_date = models.DateField(null=True, blank=True)
    source_user = models.CharField(max_length=80, blank=True)
    is_special = models.BooleanField(default=False)
    source_row_number = models.PositiveIntegerField()
    raw_data = models.JSONField(default=dict)
    linked_client = models.OneToOneField(
        Client, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='translogic_customer', verbose_name='Calculator Customer',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        constraints = [
            models.CheckConstraint(
                condition=Q(is_special=False) | Q(linked_client__isnull=True),
                name='clients_special_customer_unlinked',
            ),
        ]

    def clean(self):
        super().clean()
        if self.is_special and self.linked_client_id:
            raise ValidationError({'linked_client': 'The special Customer cannot be linked to a Calculator Customer.'})

    def __str__(self):
        return f'{self.code} — {self.name}'


def customer_import_upload_to(instance, filename):
    return f'customer_imports/{instance.pk}/{filename}'


class CustomerImport(models.Model):
    """Durable history of a confirmed Customer import."""

    filename = models.CharField(max_length=255)
    source_file = models.FileField(upload_to=customer_import_upload_to)
    sha256 = models.CharField(max_length=64)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    total_rows = models.PositiveIntegerField()
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    missing_count = models.PositiveIntegerField(default=0)
    invalid_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    special_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=30, default='IMPORTED')
    details = models.JSONField(default=dict)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Customer import'

    def __str__(self):
        return f'{self.filename} — {self.uploaded_at:%Y-%m-%d %H:%M}'


class CommercialCustomer(models.Model):
    """Commercial grouping, independent of Translogix Customer and Calculator Client."""
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=150)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Commercial Customer'

    def __str__(self):
        return f'{self.code} — {self.name}'


class CustomerSection(models.Model):
    """One source Customer code belongs to at most one commercial Customer."""
    commercial_customer = models.ForeignKey(
        CommercialCustomer, on_delete=models.PROTECT, related_name='sections')
    source_customer = models.OneToOneField(
        Customer, on_delete=models.PROTECT, related_name='commercial_section')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['source_customer__code']
        verbose_name = 'Customer Section'

    def clean(self):
        super().clean()
        if self.source_customer_id and self.source_customer.is_special:
            raise ValidationError({'source_customer': 'A special source Customer cannot be assigned as a Section.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.source_customer.code} → {self.commercial_customer.code}'
