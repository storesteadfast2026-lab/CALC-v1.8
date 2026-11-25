from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from apps.clients.models import Client
from apps.carriers.models import Carrier, CarrierService


class FreightZone(models.Model):
    """Zone mapping equivalent to the ZONES worksheet."""
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='zones')
    carrier_service = models.ForeignKey(CarrierService, on_delete=models.CASCADE)
    suburb = models.CharField(max_length=120)
    state = models.CharField(max_length=10)
    postcode = models.CharField(max_length=10, blank=True)
    zone = models.CharField(max_length=40, blank=True)
    subzone = models.CharField(max_length=40, blank=True)
    area = models.CharField(max_length=80, blank=True)
    lookup_key_suburb = models.CharField(max_length=220, db_index=True, blank=True)
    lookup_key_postcode = models.CharField(max_length=220, db_index=True, blank=True)
    source_row = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['client', 'suburb', 'state']), models.Index(fields=['client', 'postcode'])]

    def save(self, *args, **kwargs):
        carrier_key = self.carrier_service.excel_key
        self.lookup_key_suburb = f'{carrier_key}{self.suburb}{self.state}'.upper().strip()
        self.lookup_key_postcode = f'{carrier_key}{self.postcode}'.upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.carrier_service} {self.suburb}, {self.state} -> {self.zone}'


class FreightRate(models.Model):
    """Rate-card row equivalent to the RATES worksheet."""
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='rates')
    carrier_service = models.ForeignKey(CarrierService, on_delete=models.CASCADE)
    zone = models.CharField(max_length=40, blank=True)
    subzone = models.CharField(max_length=40, blank=True)
    area = models.CharField(max_length=80, blank=True)
    weight_break = models.CharField(max_length=40, blank=True)
    freight_type = models.CharField(max_length=5, blank=True)  # P or C, follows Excel OtherBrk / AV value.
    customer_code = models.CharField(max_length=30, default='STH')
    minimum_charge = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('0'))
    basic_charge = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('0'))
    per_subsequent_basic = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('0'))
    per_kg = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('0'))
    overweight_charge = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('0'))
    remote_charge = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('0'))
    offshore_charge = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('0'))
    overlength_charge = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('0'))
    margin = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal('0'))
    lookup_key = models.CharField(max_length=260, db_index=True, blank=True)
    source_row = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['client', 'lookup_key'])]

    def save(self, *args, **kwargs):
        self.lookup_key = ''.join([
            self.carrier_service.excel_key,
            self.zone or '', self.subzone or '', self.area or '',
            self.weight_break or '', self.customer_code or '', self.freight_type or ''
        ]).strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.client.code} {self.lookup_key}'


class CarrierOverlengthBreak(models.Model):
    """Carrier overlength table: SettingFlags!C22:D29 with the limits of BrokerTotals!BF:BJ.

    A band covers length_from_m up to, not including, length_to_m. A blank length_to_m has no limit.
    Editing a row moves live quotes.
    """
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='overlength_breaks')
    carrier = models.ForeignKey(Carrier, on_delete=models.CASCADE)
    tier = models.PositiveSmallIntegerField()
    length_from_m = models.DecimalField(max_digits=6, decimal_places=3)
    length_to_m = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    charge = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        unique_together = [('client', 'carrier', 'tier')]
        ordering = ['client', 'carrier', 'length_from_m']

    def clean(self):
        if self.length_from_m is None or self.client_id is None or self.carrier_id is None:
            return
        if self.length_to_m is not None and self.length_to_m <= self.length_from_m:
            raise ValidationError('The end of the band must be greater than its start.')
        others = CarrierOverlengthBreak.objects.filter(client=self.client, carrier=self.carrier).exclude(pk=self.pk)
        for other in others:
            starts_before_it_ends = other.length_to_m is None or self.length_from_m < other.length_to_m
            ends_after_it_starts = self.length_to_m is None or other.length_from_m < self.length_to_m
            if starts_before_it_ends and ends_after_it_starts:
                raise ValidationError(f'This band overlaps band {other.tier}.')

    def __str__(self):
        return f'{self.client.code} {self.carrier.code} Overlength {self.tier}'


class CarrierTailgateCharge(models.Model):
    """Carrier tailgate table equivalent to SettingFlags!C33:H52."""
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='tailgate_charges')
    carrier = models.ForeignKey(Carrier, on_delete=models.CASCADE)
    minimum_charge = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0'))
    per_subsequent_charge = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0'))
    hand_unload_charge = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0'))

    class Meta:
        unique_together = [('client', 'carrier')]

    def __str__(self):
        return f'{self.client.code} {self.carrier.code} Tailgate'
