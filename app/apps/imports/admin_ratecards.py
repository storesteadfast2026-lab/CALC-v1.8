"""STH-only upload, review and versioned load in the existing external-file registry."""
import csv
import json
from collections import Counter
from pathlib import Path
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.db import transaction
from django.utils import timezone
from apps.imports.forms import SourceUploadForm
from apps.imports.models import ExternalDataFile
from apps.imports.services.audit import create_audit_event
from apps.imports.services.csv_export import safe_csv_cell
from apps.imports.services.rate_source_load import (
    RATE_SOURCE_TYPES,
    load_source,
    prepare_source,
    rate_expression_diagnostics,
    rate_preview,
    read_source_bytes,
    rollback_source,
    zone_preview,
)
from apps.imports.services.ratecard_source import MAX_BYTES, review_ratecard
from apps.imports.services.ratecard_operational import (
    activate_operational_pair, build_operational_gate, get_operational_pair,
)
from apps.imports.services.xlsx_reader import SourceImportError, calculate_sha256
from apps.imports.services.zone_source import MAX_BYTES as ZONE_MAX_BYTES
from apps.imports.management.commands.validate_sth_rate_sources import validate_sources

REVIEW_URL = 'admin:imports_externaldatafile_ratecard_review'
EMPTY_SUMMARY = {'validation_scope': 'STRUCTURE_ONLY', 'operational_tables_updated': False,
                 'activation_allowed': False, 'quotes_use_this_file': False}
PRIORITY_REFERENCE_STATUSES = {
    'SOURCE_FIELD_REQUIRED', 'CONDITIONALLY_REACHABLE', 'EXPRESSION_REVIEW_REQUIRED',
}


class RatecardUploadForm(SourceUploadForm):
    def clean_uploaded_file(self):
        uploaded = super().clean_uploaded_file()
        if uploaded.size > MAX_BYTES:
            raise forms.ValidationError('The rate-card file must be no larger than 10 MiB.')
        return uploaded


class ZoneUploadForm(SourceUploadForm):
    def clean_uploaded_file(self):
        uploaded = super().clean_uploaded_file()
        if uploaded.size > ZONE_MAX_BYTES:
            raise forms.ValidationError('zones.csv must be no larger than 64 MiB.')
        return uploaded


class RateSourceRollbackForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}),
                             help_text='Explain why this version is being rolled back.')


class RatecardUploadAdminMixin:
    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = get_object_or_404(self.get_queryset(request), pk=object_id)
        if obj.file_type in RATE_SOURCE_TYPES and obj.client.code.upper() == 'STH':
            return self.ratecard_review_view(request, object_id)
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        return [
            path('upload-ratecards/', self.admin_site.admin_view(self.ratecard_upload_view),
                 name='imports_externaldatafile_upload_ratecards'),
            path('upload-zones/', self.admin_site.admin_view(self.zone_upload_view),
                 name='imports_externaldatafile_upload_zones'),
            path('<int:object_id>/ratecard-review/', self.admin_site.admin_view(self.ratecard_review_view),
                 name='imports_externaldatafile_ratecard_review'),
            path('<int:object_id>/rate-source-prepare/', self.admin_site.admin_view(self.rate_source_prepare_view),
                 name='imports_externaldatafile_rate_source_prepare'),
            path('<int:object_id>/rate-source-load/', self.admin_site.admin_view(self.rate_source_load_view),
                 name='imports_externaldatafile_rate_source_load'),
            path('<int:object_id>/rate-source-rollback/', self.admin_site.admin_view(self.rate_source_rollback_view),
                 name='imports_externaldatafile_rate_source_rollback'),
            path('<int:object_id>/rate-pair-diagnostic/', self.admin_site.admin_view(self.rate_pair_diagnostic_view),
                 name='imports_externaldatafile_rate_pair_diagnostic'),
            path('<int:object_id>/rate-pair-activate/', self.admin_site.admin_view(self.rate_pair_activate_view),
                 name='imports_externaldatafile_rate_pair_activate'),
        ] + super().get_urls()

    def _store_rate_source(self, request, form, *, file_type, content, summary, error, mime_type):
        name = Path(form.cleaned_data['uploaded_file'].name).name
        obj = ExternalDataFile(client=form.cleaned_data['client'], file_type=file_type,
                               source_method='ADMIN_UPLOAD', original_filename=name,
                               sha256=calculate_sha256(content), file_size_bytes=len(content),
                               mime_type=mime_type, uploaded_by=request.user,
                               notes=form.cleaned_data['notes'], validation_summary=summary,
                               validated_by=request.user, validated_at=timezone.now(),
                               status='VALIDATION_FAILED' if error else 'VALIDATED', error_message=error)
        obj.uploaded_file.save(name, ContentFile(content), save=False)
        obj.stored_path = obj.uploaded_file.name
        try:
            with transaction.atomic():
                obj.save()
                create_audit_event(event_type='RATECARD_SOURCE_REVIEWED',
                                   message=f'STH {file_type} upload and review; nothing loaded.',
                                   actor=request.user, client=obj.client, external_file=obj,
                                   metadata={'sha256': obj.sha256, 'status': obj.status,
                                             'operational_tables_updated': False}, request=request)
        except Exception:
            obj.uploaded_file.storage.delete(obj.uploaded_file.name)
            raise
        return redirect(reverse(REVIEW_URL, args=[obj.pk]))

    def ratecard_upload_view(self, request):
        if not self.has_add_permission(request) or not request.user.has_perm('imports.validate_external_data_file'):
            raise PermissionDenied('Rate-card upload requires add and validation permissions.')
        form = RatecardUploadForm(request.POST or None, request.FILES or None,
                                  expected_filename='rates_all.xls', allowed_extensions=('.xls',),
                                  allowed_clients=self._clients(request).filter(code__iexact='STH'))
        if request.method == 'POST' and form.is_valid():
            content = form.cleaned_data['uploaded_file'].read(MAX_BYTES + 1)
            name = Path(form.cleaned_data['uploaded_file'].name).name
            error = ''
            try:
                summary = review_ratecard(content, name)
                summary['load_preview'] = rate_preview(content, name, form.cleaned_data['client'])
            except SourceImportError as exc:
                summary = dict(EMPTY_SUMMARY)
                error = str(exc)
            if len(content) > MAX_BYTES:
                form.add_error('uploaded_file', 'The rate-card file must be no larger than 10 MiB.')
            else:
                return self._store_rate_source(request, form, file_type='RATES', content=content,
                                               summary=summary, error=error,
                                               mime_type='application/vnd.ms-excel')
        return TemplateResponse(request, 'admin/imports/externaldatafile/ratecard_upload.html',
                                {**self.admin_site.each_context(request), 'opts': self.model._meta,
                                 'title': 'Upload STH rate cards', 'form': form})

    def zone_upload_view(self, request):
        if not self.has_add_permission(request) or not request.user.has_perm('imports.validate_external_data_file'):
            raise PermissionDenied('Zone upload requires add and validation permissions.')
        form = ZoneUploadForm(request.POST or None, request.FILES or None,
                              expected_filename='zones.csv', allowed_extensions=('.csv',),
                              allowed_clients=self._clients(request).filter(code__iexact='STH'))
        if request.method == 'POST' and form.is_valid():
            content = form.cleaned_data['uploaded_file'].read()
            error = ''
            summary = dict(EMPTY_SUMMARY)
            try:
                summary['load_preview'] = zone_preview(content, form.cleaned_data['client'])
            except SourceImportError as exc:
                error = str(exc)
            return self._store_rate_source(request, form, file_type='ZONES', content=content,
                                           summary=summary, error=error, mime_type='text/csv')
        return TemplateResponse(request, 'admin/imports/externaldatafile/ratecard_upload.html',
                                {**self.admin_site.each_context(request), 'opts': self.model._meta,
                                 'title': 'Upload STH zones', 'form': form, 'zone_upload': True})

    def _rate_source(self, request, object_id):
        return get_object_or_404(self.get_queryset(request), pk=object_id,
                                 file_type__in=RATE_SOURCE_TYPES, client__code__iexact='STH')

    def ratecard_review_view(self, request, object_id):
        if not self.has_view_permission(request):
            raise PermissionDenied
        obj = self._rate_source(request, object_id)
        can_validate = request.user.has_perm('imports.validate_external_data_file')
        can_load = request.user.has_perm('imports.load_rate_sources')
        preview = dict((obj.validation_summary or {}).get('load_preview') or {})
        if obj.file_type == 'RATES' and 'expression_diagnostics' not in preview:
            try:
                preview['expression_diagnostics'] = rate_expression_diagnostics(
                    read_source_bytes(obj), obj.original_filename,
                )
            except SourceImportError:
                # The stored validation error remains the authoritative message.
                pass
        return TemplateResponse(request, 'admin/imports/externaldatafile/ratecard_upload.html',
                                {**self.admin_site.each_context(request), 'opts': self.model._meta,
                                 'title': f'STH {obj.get_file_type_display().lower()} source review',
                                 'source': obj, 'preview': preview,
                                 'can_prepare': can_validate and obj.status in {'UPLOADED', 'VALIDATED', 'VALIDATION_FAILED'},
                                 'can_load': can_load and obj.status == 'VALIDATED',
                                 'can_rollback': can_load and obj.status == 'ACTIVE'})

    def rate_source_prepare_view(self, request, object_id):
        self._require_permission(request, 'imports.validate_external_data_file')
        obj = self._rate_source(request, object_id)
        if request.method == 'POST':
            try:
                prepare_source(obj, actor=request.user, request=request)
            except SourceImportError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            return redirect(reverse(REVIEW_URL, args=[obj.pk]))
        return self._action_confirmation(request, obj, title='Review source', action_label='Review',
                                         explanation='This reads the file and stores no source rows.')

    def rate_source_load_view(self, request, object_id):
        self._require_permission(request, 'imports.load_rate_sources')
        obj = self._rate_source(request, object_id)
        if request.method == 'POST':
            try:
                summary = load_source(obj, actor=request.user, request=request)
                self.message_user(request, f'Loaded {summary["rows_loaded"]} rows. Quotes did not change.',
                                  messages.SUCCESS)
            except SourceImportError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            return redirect(reverse(REVIEW_URL, args=[obj.pk]))
        return self._action_confirmation(request, obj, title='Load source version', action_label='Load',
                                         explanation='This stores a version for comparison. Quotes do not use it.')

    def rate_source_rollback_view(self, request, object_id):
        self._require_permission(request, 'imports.load_rate_sources')
        obj = self._rate_source(request, object_id)
        form = RateSourceRollbackForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            try:
                rollback_source(obj, reason=form.cleaned_data['reason'], actor=request.user, request=request)
                self.message_user(request, 'Returned to the previous version. Quotes did not change.',
                                  messages.SUCCESS)
            except SourceImportError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            return redirect(reverse(REVIEW_URL, args=[obj.pk]))
        return self._action_confirmation(request, obj, title='Roll back source version', action_label='Roll back',
                                         explanation='This returns to the previous loaded version.', form=form)

    def rate_pair_diagnostic_view(self, request, object_id):
        """Compare one retained Rates source with the active Zones source; never writes data."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        rates_source = get_object_or_404(
            self.get_queryset(request), pk=object_id, file_type='RATES', client__code__iexact='STH',
        )
        zones_source = (
            ExternalDataFile.objects.filter(
                client=rates_source.client, file_type='ZONES', status='ACTIVE',
            )
            .order_by('-activated_at', '-pk')
            .first()
        )
        report = None
        error = ''
        if zones_source is None:
            error = 'No active STH Zones source is available for a paired diagnostic.'
        else:
            try:
                report = validate_sources(
                    read_source_bytes(rates_source),
                    read_source_bytes(zones_source),
                    rates_source.original_filename,
                )
            except SourceImportError as exc:
                error = str(exc)
        carriers = []
        reference_details = []
        priority_references = []
        reference_status_counts = {}
        operational_gate = None
        if report:
            operational_gate = build_operational_gate(report)
            reference_details = report['rates'].get('missing_reference_details', [])
            priority_references = [
                item for item in reference_details
                if item['review_status'] in PRIORITY_REFERENCE_STATUSES
            ]
            reference_status_counts = dict(sorted(Counter(
                item['review_status'] for item in reference_details
            ).items()))
            for name, item in report['carriers'].items():
                unresolved = [
                    {'finding': finding, 'count': count}
                    for finding, count in sorted(
                        item['unresolved'].items(), key=lambda pair: (-pair[1], pair[0]),
                    )
                ]
                carriers.append({
                    'name': name,
                    'root_card': item['root_card'],
                    'rows': item['rows'],
                    'zones_in_csv': item['zones_in_csv'],
                    'zones_with_base_price': item['zones_with_base_price'],
                    'zones_without_price': item['csv_zones_without_price'],
                    'priced_zones_missing_from_csv': item['priced_zones_missing_from_csv'],
                    'case_status': item['case_status'],
                    'base_status': item['base_status'],
                    'unresolved': unresolved,
                })
        if report and request.GET.get('format') == 'csv':
            return self._rate_pair_diagnostic_csv(
                rates_source, zones_source, report, carriers,
            )
        return TemplateResponse(
            request,
            'admin/imports/externaldatafile/rate_pair_diagnostic.html',
            {
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'title': 'STH paired Rates and Zones diagnostic',
                'rates_source': rates_source,
                'zones_source': zones_source,
                'report': report,
                'carriers': carriers,
                'priority_references': priority_references,
                'reference_status_counts': reference_status_counts,
                'operational_gate': operational_gate,
                'operational_pair': get_operational_pair(rates_source.client),
                'error': error,
            },
        )

    def rate_pair_activate_view(self, request, object_id):
        self._require_permission(request, 'imports.load_rate_sources')
        rates_source = get_object_or_404(
            self.get_queryset(request), pk=object_id, file_type='RATES',
            client__code__iexact='STH', status='ACTIVE',
        )
        if request.method != 'POST':
            raise PermissionDenied
        zones_source = (
            ExternalDataFile.objects.filter(
                client=rates_source.client, file_type='ZONES', status='ACTIVE',
            ).order_by('-activated_at', '-pk').first()
        )
        if zones_source is None:
            self.message_user(request, 'No active STH Zones source is available.', messages.ERROR)
            return redirect(reverse('admin:imports_externaldatafile_rate_pair_diagnostic', args=[rates_source.pk]))
        try:
            report = validate_sources(
                read_source_bytes(rates_source), read_source_bytes(zones_source),
                rates_source.original_filename,
            )
            gate = build_operational_gate(report)
            activate_operational_pair(
                rates_source, zones_source, gate, actor=request.user, request=request,
            )
            self.message_user(
                request,
                'Rates and Zones are now the operational STH quote sources. Only complete paths return prices.',
                messages.SUCCESS,
            )
        except (SourceImportError, ValueError) as exc:
            self.message_user(request, str(exc), messages.ERROR)
        return redirect(reverse('admin:imports_externaldatafile_rate_pair_diagnostic', args=[rates_source.pk]))

    @staticmethod
    def _rate_pair_diagnostic_csv(rates_source, zones_source, report, carriers):
        filename = f'sth_rate_diagnostic_rates_{rates_source.pk}_zones_{zones_source.pk}.csv'
        response = HttpResponse('\ufeff', content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        columns = [
            'record_type', 'rates_source_id', 'rates_sha256', 'zones_source_id', 'zones_sha256',
            'missing_card', 'review_status', 'reachable_carriers', 'from_card', 'source_row',
            'rule_name', 'customer_scope', 'condition_issue', 'expression', 'carrier', 'root_card',
            'zones_in_csv', 'zones_with_base_price', 'case_status', 'unresolved_conditions',
        ]
        writer = csv.DictWriter(response, fieldnames=columns)
        writer.writeheader()
        common = {
            'rates_source_id': rates_source.pk,
            'rates_sha256': rates_source.sha256,
            'zones_source_id': zones_source.pk,
            'zones_sha256': zones_source.sha256,
        }
        for item in report['rates'].get('missing_reference_details', []):
            for reference in item['references']:
                writer.writerow({key: safe_csv_cell(value) for key, value in {
                    **common,
                    'record_type': 'missing_reference',
                    'missing_card': item['card'],
                    'review_status': item['review_status'],
                    'reachable_carriers': '|'.join(item['reachable_carriers']),
                    'from_card': reference['from_card'],
                    'source_row': reference['row'],
                    'rule_name': reference['name'],
                    'customer_scope': reference['customer_scope'],
                    'condition_issue': reference['condition_issue'],
                    'expression': reference['expression'],
                }.items()})
        for carrier in carriers:
            writer.writerow({key: safe_csv_cell(value) for key, value in {
                **common,
                'record_type': 'carrier_summary',
                'carrier': carrier['name'],
                'root_card': carrier['root_card'],
                'zones_in_csv': carrier['zones_in_csv'],
                'zones_with_base_price': carrier['zones_with_base_price'],
                'case_status': json.dumps(carrier['case_status'], sort_keys=True),
                'unresolved_conditions': json.dumps(carrier['unresolved'], sort_keys=True),
            }.items()})
        return response
