from django.contrib import admin
from .models import FreightZone, FreightRate, CarrierTailgateCharge, CarrierOverlengthBreak

@admin.register(FreightZone)
class FreightZoneAdmin(admin.ModelAdmin):
    list_display = ('client', 'carrier_service', 'suburb', 'state', 'postcode', 'zone', 'subzone', 'area')
    list_filter = ('client', 'state', 'carrier_service')
    search_fields = ('suburb', 'postcode', 'zone')

@admin.register(FreightRate)
class FreightRateAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return False

    list_display = ('client', 'carrier_service', 'zone', 'subzone', 'area', 'weight_break', 'freight_type', 'minimum_charge', 'basic_charge')
    list_filter = ('client', 'carrier_service', 'zone', 'freight_type')
    search_fields = ('lookup_key', 'zone', 'area')

@admin.register(CarrierTailgateCharge)
class CarrierTailgateChargeAdmin(admin.ModelAdmin):
    list_display = ('client', 'carrier', 'minimum_charge', 'per_subsequent_charge', 'hand_unload_charge')
    list_filter = ('client', 'carrier')

@admin.register(CarrierOverlengthBreak)
class CarrierOverlengthBreakAdmin(admin.ModelAdmin):
    list_display = ('client', 'carrier', 'tier', 'length_from_m', 'length_to_m', 'charge')
    list_filter = ('client', 'carrier')
