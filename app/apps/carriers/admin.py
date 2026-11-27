from collections import defaultdict
from re import fullmatch

from django.contrib import admin, messages
from django.contrib.admin.templatetags.admin_list import result_headers
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, router, transaction
from django.forms import TextInput, modelform_factory
from django.http import HttpResponseRedirect
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

from .models import Carrier, CarrierService, ClientCarrierConfig


CarrierRowForm = modelform_factory(
    Carrier, fields=('code', 'name', 'active'),
    widgets={field: TextInput(attrs={'class': 'carrier-field'}) for field in ('code', 'name')},
)
ServiceRowForm = modelform_factory(
    CarrierService, fields=('service_code', 'service_name', 'active'),
    widgets={field: TextInput(attrs={'class': 'carrier-field'}) for field in ('service_code', 'service_name')},
)


class CarrierServiceInline(admin.TabularInline):
    model = CarrierService
    fields = ('service_code', 'service_name', 'active')
    extra = 0
    can_delete = False
    show_change_link = True


class ClientCarrierConfigInline(admin.TabularInline):
    model = ClientCarrierConfig
    fields = ('client', 'ratecard', 'fuel_levy', 'active')
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'carrier_service__carrier')


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    change_list_template = 'admin/carriers/carrier/change_list.html'
    list_display = ('code', 'name', 'active')
    search_fields = ('code', 'name')
    inlines = (CarrierServiceInline,)

    @method_decorator(csrf_protect)
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        context = getattr(response, 'context_data', None)
        if not context or 'cl' not in context:
            return response

        changelist = context['cl']
        service_admin = self.admin_site.get_model_admin(CarrierService)
        can_edit_carriers = self.has_change_permission(request)
        can_edit_services = service_admin.has_change_permission(request)
        can_view_services = service_admin.has_view_or_change_permission(request)
        can_add_services = service_admin.has_add_permission(request)
        saving = request.method == 'POST' and '_save' in request.POST
        if saving and not (can_edit_carriers or can_edit_services or can_add_services):
            raise PermissionDenied

        carriers = list(changelist.result_list)
        db = router.db_for_write(Carrier)
        snapshot = None
        error = None
        try:
            with transaction.atomic(using=db):
                if saving:
                    locked = Carrier.objects.using(db).filter(pk__in=[carrier.pk for carrier in carriers])
                    locked = {carrier.pk: carrier for carrier in locked.order_by('pk').select_for_update()}
                    carriers = [locked[carrier.pk] for carrier in carriers if carrier.pk in locked]

                services_by_carrier = defaultdict(list)
                if (can_view_services or can_add_services) and carriers:
                    services = CarrierService.objects.using(db).filter(carrier_id__in=[carrier.pk for carrier in carriers])
                    services = services.order_by('carrier_id', 'service_code')
                    if saving:
                        services = services.select_for_update()
                    for service in services:
                        services_by_carrier[service.carrier_id].append(service)

                snapshot = self.row_snapshot(carriers, services_by_carrier)
                if saving:
                    if not constant_time_compare(snapshot, request.POST.get('carrier_snapshot', '')):
                        self.message_user(request, 'The list changed. Review the current values and try again.', messages.WARNING)
                        return HttpResponseRedirect(request.get_full_path())
                rows, forms = self.editable_rows(
                    request, changelist, carriers, services_by_carrier, service_admin,
                    can_edit_carriers, can_edit_services, can_view_services, can_add_services, saving,
                )
                if saving:
                    if self.validate_rows(forms, services_by_carrier):
                        changed = 0
                        for model_admin, form, _, _ in forms:
                            adding = form.instance.pk is None
                            if adding or form.has_changed():
                                obj = model_admin.save_form(request, form, change=not adding)
                                model_admin.save_model(request, obj, form, change=not adding)
                                model_admin.save_related(request, form, [], change=not adding)
                                message = model_admin.construct_change_message(request, form, [], add=adding)
                                if adding:
                                    model_admin.log_addition(request, obj, message)
                                else:
                                    model_admin.log_change(request, obj, message)
                                changed += 1
                        self.message_user(request, 'Changes saved.' if changed else 'No changes to save.', messages.SUCCESS)
                        return HttpResponseRedirect(request.get_full_path())
        except IntegrityError:
            if not saving or snapshot is None:
                raise
            error = 'A database conflict prevented saving. Review the codes and try again.'

        context.update(
            carrier_rows=rows,
            carrier_headers=list(result_headers(changelist)),
            num_sorted_fields=len(changelist.get_ordering_field_columns()),
            carrier_snapshot=snapshot,
            carrier_has_forms=bool(forms or (can_add_services and rows)),
            carrier_can_view_configs=self.admin_site.get_model_admin(
                ClientCarrierConfig
            ).has_view_or_change_permission(request),
            carrier_save_error=error,
            carrier_form_errors=saving and not error,
        )
        return response

    def editable_rows(self, request, changelist, carriers, services_by_carrier, service_admin,
                      can_edit_carriers, can_edit_services, can_view_services, can_add_services, saving):
        rows = []
        forms = []
        data = request.POST if saving else None
        draft_prefixes = defaultdict(list)
        if saving:
            for key in data:
                match = fullmatch(r'(new-service-([0-9]+)-[0-9]+)-service_code', key)
                if match:
                    if not can_add_services:
                        raise PermissionDenied
                    draft_prefixes[match[2]].append(match[1])
        has_actions = 'action_checkbox' in changelist.list_display
        for carrier in carriers:
            form = None
            if can_edit_carriers:
                form = CarrierRowForm(data, instance=carrier, prefix=f'carrier-{carrier.pk}')
                forms.append((self, form, 'code', None))
            service_rows = []
            visible_services = services_by_carrier[carrier.pk] if can_view_services else ()
            for service in visible_services:
                service_form = None
                if can_edit_services:
                    service_form = ServiceRowForm(data, instance=service, prefix=f'service-{service.pk}')
                    forms.append((service_admin, service_form, 'service_code', carrier.pk))
                service_rows.append({'object': service, 'form': service_form})
            for prefix in draft_prefixes.get(str(carrier.pk), ()):
                service_form = ServiceRowForm(
                    data, instance=CarrierService(carrier=carrier),
                    prefix=prefix, use_required_attribute=False,
                )
                forms.append((service_admin, service_form, 'service_code', carrier.pk))
                service_rows.append({'form': service_form, 'is_new': True})
            new_service = None
            if can_add_services:
                new_service = {
                    'form': ServiceRowForm(
                        prefix=f'new-service-{carrier.pk}-__index__', use_required_attribute=False,
                    ),
                    'is_new': True,
                }
            rows.append({
                'object': carrier,
                'form': form,
                'checkbox': self.action_checkbox(carrier) if has_actions else None,
                'services': service_rows,
                'new_service': new_service,
            })
        return rows, forms

    @staticmethod
    def row_snapshot(carriers, services_by_carrier):
        values = [
            (carrier.pk, carrier.code, carrier.name, carrier.active, [
                (service.pk, service.service_code, service.service_name, service.active)
                for service in services_by_carrier[carrier.pk]
            ])
            for carrier in carriers
        ]
        return salted_hmac('carriers.admin.changelist', repr(values)).hexdigest()

    @staticmethod
    def validate_rows(forms, services_by_carrier):
        # Keep existing codes reserved and catch duplicates introduced together.
        reserved = defaultdict(dict)
        for scope, services in services_by_carrier.items():
            reserved[scope].update((service.service_code, service.pk) for service in services)
        for _, form, field, scope in forms:
            if scope is None:
                reserved[scope][form.initial[field]] = form.instance.pk

        valid = True
        for _, form, field, scope in forms:
            if not form.is_valid():
                valid = False
                continue
            code = form.cleaned_data[field]
            owner = form.instance.pk if form.instance.pk is not None else form.prefix
            if reserved[scope].setdefault(code, owner) != owner:
                form.add_error(field, 'This code is already in use.')
                valid = False
        return valid


@admin.register(CarrierService)
class CarrierServiceAdmin(admin.ModelAdmin):
    list_display = ('carrier', 'service_code', 'service_name', 'active')
    list_filter = ('carrier', 'active')
    inlines = (ClientCarrierConfigInline,)

    def get_model_perms(self, request):
        # Manage services from the Carriers list.
        return {}


@admin.register(ClientCarrierConfig)
class ClientCarrierConfigAdmin(admin.ModelAdmin):
    list_display = ('client', 'carrier_service', 'base_status', 'customer_code', 'ratecard', 'fuel_levy', 'fuel_levy_source', 'fuel_levy_updated_at', 'cubic_conversion', 'tailgate_enabled', 'pallet_enabled', 'carton_enabled', 'active')
    list_filter = ('client', 'active', 'base_status', 'fuel_levy_source', 'tailgate_enabled', 'pallet_enabled', 'carton_enabled', 'zone_enabled', 'postcode_zones_enabled')
    search_fields = ('carrier_service__carrier__code', 'carrier_service__service_code', 'ratecard')

    readonly_fields = ('fuel_levy_source', 'fuel_levy_updated_at', 'fuel_data_file')
