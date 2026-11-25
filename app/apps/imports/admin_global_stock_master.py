"""Admin upload and read-only Preview for Global Stock Master Phase 1."""

from hashlib import sha256
from pathlib import Path

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.authentication_gateway.services import is_django_administrator
from apps.clients.models import Customer
from apps.imports.models import StockMaster
from apps.imports.services.global_stock_reconciliation import global_stock_product_reconciliation
from apps.imports.services.xlsx_reader import normalize_product_sku
from apps.imports.services.audit import create_audit_event
from apps.imports.services.global_stock_master import (
    authorised_stock_client,
    customer_resolution_summary,
    stock_master_comparison,
    validate_stock_master,
)
from apps.imports.services.xlsx_reader import SourceImportError


class StockMasterUploadForm(forms.Form):
    original_file = forms.FileField(label='Global stock.xls (or controlled .xls extract)')

    def clean_original_file(self):
        upload = self.cleaned_data['original_file']
        if Path(upload.name).suffix.lower() != '.xls':
            raise forms.ValidationError(
                'Select the global stock.xls workbook or a controlled .xls extract.'
            )
        if not 0 < upload.size <= 64 * 1024 * 1024:
            raise forms.ValidationError('The workbook must be between 1 byte and 64 MB.')
        return upload


class GlobalReconciliationFilterForm(forms.Form):
    """Exact-match, GET-only filters for the global informational comparison."""

    customer = forms.CharField(required=False, max_length=100, label='Source Customer')
    sku = forms.CharField(required=False, max_length=255, label='SKU (normalised)')
    status = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All comparison statuses'),
            ('MATCHED', 'Matched'),
            ('STOCK_ONLY', 'Stock only'),
            ('PRODUCT_MASTER_ONLY', 'Product Master only'),
            ('AMBIGUOUS_PRODUCT_MASTER', 'Ambiguous Product Master'),
        ],
    )


class StockMasterDetailsFilterForm(forms.Form):
    """GET-only, exact-match filters; no Customer-to-Client mapping is implied."""

    customer = forms.CharField(required=False, max_length=100, label='Source Customer')
    sku = forms.CharField(required=False, max_length=255, label='SKU (normalised)')
    serial_no = forms.CharField(required=False, max_length=255, label='Serial no.')


@admin.register(StockMaster)
class StockMasterAdmin(admin.ModelAdmin):
    change_list_template = 'admin/imports/file_history.html'
    list_display = ('original_filename', 'status', 'uploaded_at', 'uploaded_by', 'sha256')
    ordering = ('-uploaded_at',)
    search_fields = ('original_filename', 'sha256')
    list_filter = ('status',)

    def get_model_perms(self, request):
        """Use Stock Masters contextually from Import Centre, not as a menu."""
        return {}

    def has_module_permission(self, request):
        return is_django_administrator(request.user)

    def has_view_permission(self, request, obj=None):
        return is_django_administrator(request.user)

    def has_add_permission(self, request):
        return is_django_administrator(request.user)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _require_admin(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied('Stock Master requires a Django administrator.')

    def get_urls(self):
        return [
            path(
                '<int:master_id>/global-reconciliation/',
                self.admin_site.admin_view(self.global_reconciliation_view),
                name='imports_stockmaster_global_reconciliation',
            ),
            path(
                '<int:master_id>/global-details/',
                self.admin_site.admin_view(self.global_details_view),
                name='imports_stockmaster_global_details',
            ),
            path(
                '<int:master_id>/compare/<int:client_id>/',
                self.admin_site.admin_view(self.compare_view),
                name='imports_stockmaster_compare',
            ),
            path(
                '<int:master_id>/validate/',
                self.admin_site.admin_view(self.validate_view),
                name='imports_stockmaster_validate',
            ),
        ] + super().get_urls()

    def add_view(self, request, form_url='', extra_context=None):
        self._require_admin(request)
        form = StockMasterUploadForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            upload = form.cleaned_data['original_file']
            content = upload.read()
            master = StockMaster(
                original_filename=Path(upload.name).name,
                sha256=sha256(content).hexdigest(),
                file_size_bytes=len(content),
                uploaded_by=request.user,
            )
            master.original_file.save(master.original_filename, ContentFile(content), save=False)
            master.save()
            create_audit_event(
                event_type='STOCK_MASTER_UPLOADED',
                message=f'Global Stock Master #{master.pk} uploaded.',
                actor=request.user,
                metadata={
                    'stock_master_id': master.pk,
                    'sha256': master.sha256,
                    'filename': master.original_filename,
                    'operational_tables_updated': False,
                },
                request=request,
            )
            return redirect(reverse('admin:imports_stockmaster_change', args=[master.pk]))
        return TemplateResponse(
            request,
            'admin/imports/stockmaster/upload.html',
            {
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'title': 'Upload Global Stock Master',
                'form': form,
            },
        )

    def change_view(self, request, object_id, form_url='', extra_context=None):
        self._require_admin(request)
        if request.method != 'GET':
            return HttpResponseNotAllowed(['GET'])
        master = get_object_or_404(self.get_queryset(request), pk=object_id)
        summary = dict(master.validation_summary or {})
        linked_customers = []
        if master.status == 'VALIDATED':
            summary.update(customer_resolution_summary(master.source_rows.all()))
            linked_customers = list(
                Customer.objects.filter(
                    code__in=summary.get('customer_counts', {}),
                    linked_client__isnull=False,
                    is_special=False,
                )
                .select_related('linked_client')
                .order_by('code')
            )
        return TemplateResponse(
            request,
            'admin/imports/stockmaster/preview.html',
            {
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'title': 'Stock — Summary',
                'master': master,
                'summary': summary,
                'linked_customers': linked_customers,
            },
        )

    def global_details_view(self, request, master_id):
        """Browse raw staged lines for *any* source Customer, with no writes."""
        self._require_admin(request)
        if request.method != 'GET':
            return HttpResponseNotAllowed(['GET'])
        master = get_object_or_404(
            self.get_queryset(request), pk=master_id, status='VALIDATED'
        )
        form = StockMasterDetailsFilterForm(request.GET)
        # An explicitly empty Customer filter selects source rows whose
        # Customer was blank; absent customer= means *all* source Customers.
        customer_filter_active = 'customer' in request.GET
        rows = master.source_rows.all().order_by('source_row_number', 'pk')
        if form.is_valid():
            if customer_filter_active:
                rows = rows.filter(customer_code=form.cleaned_data['customer'])
            if form.cleaned_data['sku']:
                rows = rows.filter(
                    product_code_normalized=normalize_product_sku(form.cleaned_data['sku'])
                )
            if form.cleaned_data['serial_no']:
                rows = rows.filter(serial_no=form.cleaned_data['serial_no'])
        else:
            # Never broaden an invalid filter into an accidental global query.
            rows = rows.none()
        page = Paginator(rows, 100).get_page(request.GET.get('page'))
        return TemplateResponse(
            request,
            'admin/imports/stockmaster/global_details.html',
            {
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'title': 'Stock — File rows',
                'master': master,
                'filter_form': form,
                'customer_filter_active': customer_filter_active,
                'row_page': page,
            },
        )

    def global_reconciliation_view(self, request, master_id):
        """Read-only company-wide Stock vs latest validated Product Master."""
        self._require_admin(request)
        if request.method != 'GET':
            return HttpResponseNotAllowed(['GET'])
        master = get_object_or_404(
            self.get_queryset(request), pk=master_id, status='VALIDATED'
        )
        form = GlobalReconciliationFilterForm(request.GET)
        if not form.is_valid():
            # Invalid filters must not silently expand to the complete dataset.
            rows = []
            workspace = None
        else:
            try:
                workspace = global_stock_product_reconciliation(master)
            except SourceImportError as exc:
                workspace = None
                form.add_error(None, str(exc))
                rows = []
            else:
                rows = workspace['entries']
                if 'customer' in request.GET:
                    customer_code = request.GET['customer'].strip().upper()
                    rows = [row for row in rows if row['customer'] == customer_code]
                if form.cleaned_data['sku']:
                    sku = normalize_product_sku(form.cleaned_data['sku'])
                    rows = [row for row in rows if row['sku'] == sku]
                if form.cleaned_data['status']:
                    rows = [row for row in rows if row['status'] == form.cleaned_data['status']]
        page = Paginator(rows, 50).get_page(request.GET.get('page'))
        return TemplateResponse(
            request, 'admin/imports/stockmaster/global_reconciliation.html',
            {
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'title': 'Stock — Compare with Products file',
                'master': master,
                'filter_form': form,
                'customer_filter_active': 'customer' in request.GET,
                'row_page': page,
                'workspace': workspace,
                'show_incomplete_rows': request.GET.get('incomplete') == '1',
            },
        )

    def validate_view(self, request, master_id):
        self._require_admin(request)
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        master = get_object_or_404(self.get_queryset(request), pk=master_id)
        try:
            master = validate_stock_master(master.pk, actor=request.user)
            create_audit_event(
                event_type='STOCK_MASTER_VALIDATED',
                message=f'Global Stock Master #{master.pk}: {master.status}.',
                actor=request.user,
                metadata={
                    'stock_master_id': master.pk,
                    'sha256': master.sha256,
                    'status': master.status,
                    'operational_tables_updated': False,
                },
                request=request,
            )
            if master.status == 'VALIDATION_FAILED':
                self.message_user(request, master.error_message, messages.ERROR)
            else:
                self.message_user(
                    request,
                    'Stock Master validated. No operational data changed.',
                    messages.SUCCESS,
                )
        except SourceImportError as exc:
            self.message_user(request, str(exc), messages.ERROR)
        return redirect(reverse('admin:imports_stockmaster_change', args=[master.pk]))

    def compare_view(self, request, master_id, client_id):
        self._require_admin(request)
        if request.method != 'GET':
            return HttpResponseNotAllowed(['GET'])
        client = authorised_stock_client(request.user, client_id)
        master = get_object_or_404(StockMaster, pk=master_id, status='VALIDATED')
        workspace = stock_master_comparison(master, client)
        workspace['row_page'] = Paginator(workspace['rows'], 50).get_page(
            request.GET.get('page')
        )
        workspace['raw_page'] = Paginator(workspace['raw_rows'], 100).get_page(
            request.GET.get('raw_page')
        )
        workspace['operational_only_page'] = Paginator(
            workspace['operational_only'], 50
        ).get_page(request.GET.get('product_page'))
        return TemplateResponse(
            request,
            'admin/imports/stockmaster/comparison.html',
            {
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'title': f'Stock — Compare with customer products — {client.code}',
                'master': master,
                **workspace,
            },
        )
