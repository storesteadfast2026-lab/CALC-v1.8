"""Customer master and Calculator Customer administration."""

import hashlib
import logging
import tempfile
import uuid
from pathlib import Path

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.admin.widgets import AutocompleteSelectMultiple
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from apps.authentication_gateway.services import is_django_administrator

from .customer_import import (
    MAX_UPLOAD_BYTES, CustomerImportError, import_customers,
    master_state_digest, preview_customers,
)
from .calculator_customer_enable import CalculatorCustomerConflict, enable_calculator_customer
from .models import Client, Customer, CustomerImport, FreightCalculator


logger = logging.getLogger(__name__)


class FreightCalculatorAdminForm(forms.ModelForm):
    def clean_client(self):
        client = self.cleaned_data['client']
        if client.calculators.filter(archived_at__isnull=True).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This client already has a freight calculator. Edit the existing one.')
        return client

    class Meta:
        model = FreightCalculator
        fields = '__all__'
        help_texts = {
            'cubic_margin_options': (
                'Enter whole numbers from 0 to 20 in brackets, without % signs. '
                'Use [] for 0% only, or [0, 5, 10] to offer 0%, 5% and 10%.'
            ),
        }


@admin.register(FreightCalculator)
class FreightCalculatorAdmin(admin.ModelAdmin):
    form = FreightCalculatorAdminForm
    list_display = ('client', 'name', 'version', 'active', 'cubic_margin_enabled',
                    'custom_freight_enabled', 'visible_history_days')
    list_filter = ('active', 'cubic_margin_enabled', 'custom_freight_enabled')
    search_fields = ('client__code', 'client__name', 'name', 'version')
    autocomplete_fields = ('client',)
    fieldsets = (
        (None, {'fields': ('client', 'name', 'version', 'active')}),
        ('Customer options', {'fields': (
            'custom_freight_enabled', 'cubic_margin_enabled',
            'cubic_margin_options', 'visible_history_days',
        )}),
        ('Technical settings', {'fields': ('calculation_engine_key',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(archived_at__isnull=True)


class EnableCalculatorCustomerForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(), label='Customer', empty_label='Select a Customer',
    )
    active = forms.BooleanField(label='Active', required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = (
            Customer.objects.filter(is_special=False, linked_client__isnull=True)
            .exclude(code='*').order_by('code')
        )


class CustomerUploadForm(forms.Form):
    file = forms.FileField(label='Customer workbook (.xls)')

    def clean_file(self):
        upload = self.cleaned_data['file']
        if Path(upload.name).suffix.lower() != '.xls' or upload.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError('Select a legacy .xls workbook of no more than 5 MB.')
        return upload


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    add_form_template = 'admin/clients/client/add_form.html'
    list_display = ('code', 'name', 'dimension_fallback_source',
                    'cubic_dimension_confirmation_factor', 'active',
                    'translogic_link', 'updated_at')
    list_filter = ('dimension_fallback_source', 'active')
    search_fields = ('code', 'name')

    def add_view(self, request, form_url='', extra_context=None):
        """Require Customer selection on the existing Admin add URL, including direct POSTs."""
        if not self.has_add_permission(request) or not is_django_administrator(request.user):
            raise PermissionDenied('Freight Account creation requires an administrator.')
        form = EnableCalculatorCustomerForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            try:
                customer = form.cleaned_data['customer']
                client, created = enable_calculator_customer(
                    customer.pk, active=form.cleaned_data['active'],
                )
                self.message_user(
                    request,
                    f'Freight Account {client.code} {"created" if created else "linked"} from Customer {customer.code}.',
                    messages.SUCCESS,
                )
                return HttpResponseRedirect(reverse('admin:clients_client_change', args=[client.pk]))
            except (CalculatorCustomerConflict, Customer.DoesNotExist) as exc:
                form.add_error('customer', str(exc))
        context = {
            **self.admin_site.each_context(request), 'opts': self.model._meta,
            'title': 'Add Freight Account', 'form': form,
        }
        return TemplateResponse(request, self.add_form_template, context)

    @admin.display(description='Translogic Customer')
    def translogic_link(self, obj):
        try:
            return obj.translogic_customer.code
        except Customer.DoesNotExist:
            return '—'


class LinkedFilter(admin.SimpleListFilter):
    title = 'Calculator Customer link'
    parameter_name = 'linked'

    def lookups(self, request, model_admin):
        return (('yes', 'Linked'), ('no', 'Unlinked'))

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(linked_client__isnull=False)
        if self.value() == 'no':
            return queryset.filter(linked_client__isnull=True)
        return queryset


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    change_form_template = 'admin/clients/customer/change_form.html'
    list_display = ('code', 'name', 'group', 'group1', 'group2', 'wh_pick_code',
                    'source_date', 'linked_client', 'calculator_customer_status', 'is_special')
    search_fields = ('code', 'name', 'group', 'group1', 'group2')
    list_filter = ('group', 'group1', 'group2', 'is_special', LinkedFilter)
    list_select_related = ('linked_client',)
    readonly_fields = ('code', 'name', 'group', 'group1', 'group2', 'their_code',
                       'wh_pick_code', 'acn', 'abn', 'gst_code', 'sett_days',
                       'paydays_type', 'source_date', 'source_user', 'is_special',
                       'source_row_number', 'raw_data', 'created_at', 'updated_at',
                       'calculator_customer_link', 'calculator_customer_status')
    fields = readonly_fields

    @admin.display(description='Calculator Customer')
    def calculator_customer_link(self, obj):
        return obj.linked_client.code if obj and obj.linked_client_id else '—'

    @admin.display(description='Status')
    def calculator_customer_status(self, obj):
        return 'Linked' if obj and obj.linked_client_id else 'Not linked'

    def has_module_permission(self, request):
        return is_django_administrator(request.user)

    def has_view_permission(self, request, obj=None):
        return is_django_administrator(request.user)

    def has_change_permission(self, request, obj=None):
        # Customer master fields and links change through the import or enable service.
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [
            path('import/', self.admin_site.admin_view(self.import_view),
                 name='clients_customer_import'),
            path('<int:customer_id>/enable/', self.admin_site.admin_view(self.enable_view),
                 name='clients_customer_enable'),
        ] + super().get_urls()

    def enable_view(self, request, customer_id):
        if not is_django_administrator(request.user):
            raise PermissionDenied('Calculator Customer creation requires an administrator.')
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        try:
            client, created = enable_calculator_customer(customer_id, active=True)
            self.message_user(
                request,
                f'Calculator Customer {client.code} {"created" if created else "linked"}.',
                messages.SUCCESS,
            )
            return HttpResponseRedirect(reverse('admin:clients_customer_change', args=[customer_id]))
        except (CalculatorCustomerConflict, Customer.DoesNotExist) as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return HttpResponseRedirect(reverse('admin:clients_customer_change', args=[customer_id]))

    def import_view(self, request):
        if not is_django_administrator(request.user):
            raise PermissionDenied('Customer imports require an administrator.')
        preview, token, error, filename = None, None, None, None
        form = CustomerUploadForm()
        if request.method == 'POST' and request.POST.get('action') == 'validate':
            form = CustomerUploadForm(request.POST, request.FILES)
            if form.is_valid():
                upload = form.cleaned_data['file']
                filename = Path(upload.name).name
                content = upload.read()
                try:
                    preview = preview_customers(content)
                    directory = Path(tempfile.gettempdir()) / 'calculator_customer_previews'
                    directory.mkdir(mode=0o700, exist_ok=True)
                    name = f'{uuid.uuid4().hex}.xls'
                    (directory / name).write_bytes(content)
                    token = signing.dumps({
                        'file': name, 'filename': filename,
                        'user': request.user.pk, 'sha256': hashlib.sha256(content).hexdigest(),
                        'state': master_state_digest(),
                    }, salt='customer-import-preview')
                    logger.info('Customer XLS validated: user=%s filename=%s sha256=%s rows=%s invalid=%s duplicates=%s',
                                request.user.pk, filename, hashlib.sha256(content).hexdigest(),
                                preview.total_rows, len(preview.errors), len(preview.duplicates))
                except CustomerImportError as exc:
                    error = str(exc)
                    logger.warning('Customer XLS validation failed: user=%s filename=%s reason=%s',
                                   request.user.pk, filename, error)
        elif request.method == 'POST' and request.POST.get('action') == 'import':
            try:
                payload = signing.loads(request.POST.get('token', ''),
                                        salt='customer-import-preview', max_age=1800)
                if payload['user'] != request.user.pk:
                    raise CustomerImportError('This preview belongs to another user.')
                name = payload['file']
                if Path(name).name != name or not name.endswith('.xls'):
                    raise CustomerImportError('Invalid preview reference.')
                source = Path(tempfile.gettempdir()) / 'calculator_customer_previews' / name
                content = source.read_bytes()
                history = import_customers(
                    content, filename=payload['filename'], actor=request.user,
                    expected_digest=payload['sha256'], expected_state=payload['state'],
                    request=request,
                )
                source.unlink(missing_ok=True)
                self.message_user(request, f'Imported {history.created_count} new and '
                                  f'{history.updated_count} changed Customers.', messages.SUCCESS)
                return HttpResponseRedirect(reverse('admin:clients_customer_changelist'))
            except (CustomerImportError, signing.BadSignature, KeyError, OSError) as exc:
                error = str(exc)
        context = {
            **self.admin_site.each_context(request), 'opts': self.model._meta,
            'title': 'Import Customers', 'form': form, 'preview': preview,
            'token': token, 'error': error, 'filename': filename,
        }
        return TemplateResponse(request, 'admin/clients/customer/import.html', context)


@admin.register(CustomerImport)
class CustomerImportAdmin(admin.ModelAdmin):
    list_display = ('filename', 'uploaded_at', 'uploaded_by', 'total_rows',
                    'created_count', 'updated_count', 'unchanged_count', 'missing_count', 'status')
    readonly_fields = ('filename', 'source_file', 'sha256', 'uploaded_at',
                       'uploaded_by', 'total_rows', 'created_count', 'updated_count',
                       'unchanged_count', 'missing_count', 'invalid_count',
                       'duplicate_count', 'special_count', 'status', 'details')
    fields = readonly_fields

    def get_model_perms(self, request):
        # Customer import history is linked from Import Centre.
        return {}

    def has_module_permission(self, request):
        return is_django_administrator(request.user)

    def has_view_permission(self, request, obj=None):
        return is_django_administrator(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Commercial groupings never create or enable Calculator Clients.
from .models import CommercialCustomer, CustomerSection


class CommercialCustomerCodeWidget(AutocompleteSelectMultiple):
    def get_url(self):
        return reverse(f'{self.admin_site.name}:clients_commercialcustomer_code_search')


class CommercialCustomerCodeSearch(AutocompleteJsonView):
    def process_request(self, request):
        return (
            request.GET.get('term', ''),
            self.admin_site.get_model_admin(Customer),
            CustomerSection._meta.get_field('source_customer'),
            'pk',
        )

    def get_queryset(self):
        return super().get_queryset().filter(is_special=False).select_related(
            'commercial_section__commercial_customer',
        )

    def serialize_result(self, obj, to_field_name):
        result = super().serialize_result(obj, to_field_name)
        section = getattr(obj, 'commercial_section', None)
        if section:
            result['text'] = f'{obj} (linked to {section.commercial_customer.code})'
            result['disabled'] = True
        return result


class CustomerLinksToRemoveField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, section):
        return f'Unlink {section.source_customer}'


class CommercialCustomerAdminForm(forms.ModelForm):
    customer_links_to_remove = CustomerLinksToRemoveField(
        label='Unlink customer codes',
        queryset=CustomerSection.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    customer_codes_to_add = forms.ModelMultipleChoiceField(
        label='Add customer codes',
        queryset=Customer.objects.filter(is_special=False),
        required=False,
        widget=CommercialCustomerCodeWidget(
            CustomerSection._meta.get_field('source_customer'), admin.site,
            attrs={'data-placeholder': 'Search by code or name'},
        ),
        help_text='Select one or more codes, then click Save.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get('customer_links_to_remove')
        if field is None:
            return
        if self.instance.pk:
            field.queryset = self.instance.sections.select_related('source_customer')
        if field.queryset.exists():
            field.help_text = 'Tick the codes you want to unlink, then click Save.'
        else:
            field.help_text = 'No customer codes linked.'

    def clean_customer_codes_to_add(self):
        selected = self.cleaned_data['customer_codes_to_add']
        # The admin saves the form in a transaction. Lock the source customers
        # before checking links so simultaneous additions are checked in order.
        customers = list(selected.select_for_update().order_by('pk'))
        existing = {
            section.source_customer_id: section
            for section in CustomerSection.objects.filter(source_customer__in=customers)
            .select_related('commercial_customer')
        }
        new_customers = []
        for customer in customers:
            section = existing.get(customer.pk)
            if section is None:
                new_customers.append(customer)
            elif section.commercial_customer_id != self.instance.pk:
                raise forms.ValidationError(
                    '%(code)s is already linked to %(commercial_code)s.',
                    params={'code': customer.code, 'commercial_code': section.commercial_customer.code},
                )
        return new_customers


@admin.register(CommercialCustomer)
class CommercialCustomerAdmin(admin.ModelAdmin):
    form = CommercialCustomerAdminForm
    list_display = ('code', 'name', 'section_count')
    search_fields = ('code', 'name')
    fieldsets = (
        (None, {'fields': ('code', 'name', 'notes')}),
        ('Linked customer codes', {'fields': ('customer_links_to_remove', 'customer_codes_to_add')}),
    )

    def get_urls(self):
        return [
            path(
                'customer-code-search/',
                self.admin_site.admin_view(CommercialCustomerCodeSearch.as_view(admin_site=self.admin_site)),
                name='clients_commercialcustomer_code_search',
            ),
        ] + super().get_urls()

    def render_change_form(self, request, context, *args, **kwargs):
        context.update(show_save_and_continue=False, show_save_and_add_another=False)
        return super().render_change_form(request, context, *args, **kwargs)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.unlinked_customer_codes = []
        selected_links = form.cleaned_data['customer_links_to_remove']
        for section in selected_links.select_for_update(of=('self',)).order_by('pk'):
            form.unlinked_customer_codes.append(str(section.source_customer))
            section.delete()
        for customer in form.cleaned_data['customer_codes_to_add']:
            CustomerSection.objects.create(commercial_customer=form.instance, source_customer=customer)

    def construct_change_message(self, request, form, formsets, add=False):
        message = super().construct_change_message(request, form, formsets, add)
        for customer_code in form.unlinked_customer_codes:
            message.append({'deleted': {'name': 'customer code link', 'object': customer_code}})
        return message

    def has_module_permission(self, request):
        return is_django_administrator(request.user)

    def has_view_permission(self, request, obj=None):
        return is_django_administrator(request.user)

    def has_add_permission(self, request):
        return is_django_administrator(request.user)

    def has_change_permission(self, request, obj=None):
        return is_django_administrator(request.user)

    def has_delete_permission(self, request, obj=None):
        return False  # Retain auditable commercial grouping history.

    @admin.display(description='Sections')
    def section_count(self, obj):
        return obj.sections.count()


@admin.register(CustomerSection)
class CustomerSectionAdmin(admin.ModelAdmin):
    list_display = ('source_customer', 'commercial_customer', 'created_at')
    list_select_related = ('source_customer', 'commercial_customer')
    search_fields = ('source_customer__code', 'commercial_customer__code')
    readonly_fields = ('created_at', 'unlink_customer_code')

    @admin.display(description='Unlink customer code')
    def unlink_customer_code(self, obj):
        if not obj or not obj.pk:
            return None
        url = reverse(
            f'{self.admin_site.name}:clients_commercialcustomer_change',
            args=[obj.commercial_customer_id],
        )
        return format_html(
            '<a href="{}#id_customer_links_to_remove">Unlink {} in {}</a>',
            url, obj.source_customer.code, obj.commercial_customer.code,
        )

    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return is_django_administrator(request.user)

    def has_add_permission(self, request):
        return is_django_administrator(request.user)

    def has_change_permission(self, request, obj=None):
        return is_django_administrator(request.user)

    def has_delete_permission(self, request, obj=None):
        return False  # Explicit reassignment rather than silent deletion.
