from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.authentication_gateway.services import (
    CalculatorAccessDenied,
    allowed_clients_for,
)
from apps.clients.models import Client
from apps.imports.models import (
    ExternalDataFile, FtpImportConfiguration, FtpImportSchedule,
    ProductMaster, StockMaster,
)
from apps.imports.services.ftp_automation import process_ftp_configuration
from apps.imports.services.ftp_inbox import ftp_uploaded_data_root
from apps.imports.services.ratecard_operational import get_operational_pair


FTP_FILE_CHOICES = (
    ('PRODUCTS|products.xls', 'Products — products.xls'),
    ('STOCK|stock.xls', 'Stock — stock.xls'),
    ('FUEL|fuel.xls', 'Fuel — fuel.xls'),
    ('SUBURBS|postcodes.xls', 'Suburbs / postcodes — postcodes.xls'),
    ('RATES|rates_all.xls', 'Rates — rates_all.xls'),
    ('ZONES|zones.csv', 'Zones — zones.csv'),
)

FTP_UPLOAD_DEFINITIONS = {
    'products': {
        'file_type': 'PRODUCTS',
        'filename': 'products.xls',
        'extensions': ('.xls', '.xlsx', '.csv'),
    },
    'stock': {
        'file_type': 'STOCK',
        'filename': 'stock.xls',
        'extensions': ('.xls', '.xlsx', '.csv'),
    },
    'fuel': {
        'file_type': 'FUEL',
        'filename': 'fuel.xls',
        'extensions': ('.xls', '.csv'),
    },
    'suburbs': {
        'file_type': 'SUBURBS',
        'filename': 'postcodes.xls',
        'extensions': ('.xls', '.csv'),
    },
    'rates': {
        'file_type': 'RATES',
        'filename': 'rates_all.xls',
        'extensions': ('.xls',),
    },
    'zones': {
        'file_type': 'ZONES',
        'filename': 'zones.csv',
        'extensions': ('.csv',),
    },
}

FTP_UPLOAD_KEY_BY_TYPE = {
    definition['file_type']: key
    for key, definition in FTP_UPLOAD_DEFINITIONS.items()
}


class FtpImportScheduleForm(forms.ModelForm):
    run_today = forms.BooleanField(
        label='Run at the scheduled time today',
        required=False,
        help_text=(
            'Use this for one check today, even if the files were already checked. '
            'By default, a schedule change starts on the next enabled day.'
        ),
    )
    enabled_files = forms.MultipleChoiceField(
        label='Files to process',
        required=False,
        choices=FTP_FILE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text=(
            'Select one or more files. The selection will apply to all active '
            'clients when you save the schedule.'
        ),
    )

    class Meta:
        model = FtpImportSchedule
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            return
        enabled = {
            f'{file_type}|{filename}'
            for file_type, filename in FtpImportConfiguration.objects.filter(
                active=True,
            ).values_list('file_type', 'filename')
        }
        self.initial['enabled_files'] = [
            key for key, _label in FTP_FILE_CHOICES if key in enabled
        ]

    def clean(self):
        cleaned = super().clean()
        run_time = cleaned.get('run_time')
        enabled_days = {
            index for index, day in enumerate(FtpImportSchedule.WEEKDAY_FIELDS)
            if cleaned.get(day)
        }
        if run_time is None or self.errors:
            return cleaned

        current_time = timezone.now()
        schedule_timezone = timezone.get_default_timezone()
        today = timezone.localdate(current_time, schedule_timezone)
        schedule_fields = ('run_time', 'active', *FtpImportSchedule.WEEKDAY_FIELDS)
        if cleaned.get('run_today'):
            starts_at = timezone.make_aware(
                datetime.combine(today, run_time), schedule_timezone,
            )
            if not cleaned.get('active') or today.weekday() not in enabled_days:
                self.add_error('run_today', 'Activate the schedule and enable today first.')
            elif starts_at <= current_time:
                self.add_error('run_today', 'Choose a time later than the current Adelaide time.')
            else:
                self.instance.starts_at = starts_at
        elif enabled_days and (
            self.instance._state.adding or any(field in self.changed_data for field in schedule_fields)
        ):
            days_until_start = min((day - today.weekday() - 1) % 7 + 1 for day in enabled_days)
            start_day = today + timedelta(days=days_until_start)
            self.instance.starts_at = timezone.make_aware(
                datetime.combine(start_day, run_time), schedule_timezone,
            )
        return cleaned


@admin.register(FtpImportSchedule)
class FtpImportScheduleAdmin(admin.ModelAdmin):
    form = FtpImportScheduleForm
    change_form_template = 'admin/imports/ftpimportschedule/change_form.html'
    list_display = ('run_time', 'selected_days', 'active', 'retry_minutes', 'updated_at')
    fields = (
        'active',
        'run_time',
        ('monday', 'tuesday', 'wednesday', 'thursday', 'friday'),
        ('saturday', 'sunday'),
        'run_today',
        'schedule_start',
        'retry_minutes',
        'enabled_files',
        'updated_at',
    )
    readonly_fields = ('schedule_start', 'updated_at')

    @admin.display(description='Schedule starts')
    def schedule_start(self, obj):
        if not obj or not obj.active or not obj.starts_at:
            return None
        starts_at = timezone.localtime(obj.starts_at, timezone.get_default_timezone())
        return starts_at.strftime('%a %d %b %Y, %H:%M:%S %Z')

    def get_urls(self):
        custom_urls = [
            path(
                'check-inbox-now/',
                self.admin_site.admin_view(self.check_inbox_now_view),
                name='imports_ftpimportschedule_check_inbox_now',
            ),
            path(
                'upload/<slug:file_key>/',
                self.admin_site.admin_view(self.upload_now_view),
                name='imports_ftpimportschedule_upload_now',
            ),
            path(
                'status/<slug:file_key>/',
                self.admin_site.admin_view(self.file_status_view),
                name='imports_ftpimportschedule_file_status',
            ),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        """The Import Centre is a singleton, so skip the intermediate list."""
        schedule = FtpImportSchedule.objects.order_by('pk').first()
        if schedule is None:
            return redirect('admin:imports_ftpimportschedule_add')
        return redirect('admin:imports_ftpimportschedule_change', schedule.pk)

    def _clients(self, request):
        if request.user.is_superuser:
            return Client.objects.filter(active=True)
        try:
            return allowed_clients_for(request.user).filter(active=True)
        except CalculatorAccessDenied:
            return Client.objects.none()

    @staticmethod
    def _has_active_product_apply(external_file):
        batches = (
            (external_file.import_summary or {}).get(
                'product_reconciliation_apply_batches',
            )
            or []
        )
        return any(
            batch.get('batch_id') and not batch.get('rolled_back_at')
            for batch in batches
        )

    def _operational_state(self, file_type, file_snapshots):
        """Describe real calculator use, independently from schedule/import status."""
        snapshots = list(file_snapshots)
        latest = snapshots[0] if snapshots else None

        if file_type == 'STOCK':
            master = StockMaster.objects.filter(status='VALIDATED').first()
            if master:
                rows = int((master.validation_summary or {}).get('rows_valid', 0))
                return {
                    'label': 'In use (informational)',
                    'tone': 'operational',
                    'detail': (
                        f'Current company-wide inventory source: {master.original_filename} '
                        f'({rows:,} valid rows). '
                        'It does not block or change freight quotes.'
                    ),
                }
            return {
                'label': 'Not activated',
                'tone': 'reference',
                'detail': (
                    'No current inventory source is selected. Stock never blocks '
                    'or changes freight quotes.'
                ),
            }

        if file_type in {'RATES', 'ZONES'}:
            client_ids = {item.client_id for item in snapshots}
            for client_id in client_ids:
                client = Client.objects.filter(pk=client_id).first()
                pair = get_operational_pair(client) if client else None
                if not pair:
                    continue
                rates_source, zones_source = pair
                active = rates_source if file_type == 'RATES' else zones_source
                validation = (active.import_summary or {}).get(
                    'operational_validation',
                ) or {}
                warning_count = len(validation.get('warnings') or [])
                warning_detail = (
                    f' {warning_count} non-blocking validation warning(s) remain for '
                    'later review.'
                    if warning_count else ''
                )
                return {
                    'label': 'In use — validation passed',
                    'tone': 'operational',
                    'detail': (
                        f'{active.original_filename} is the active operational source '
                        f'for STH quotes.{warning_detail}'
                    ),
                }
            return {
                'label': 'Validation required — baseline in use',
                'tone': 'baseline',
                'detail': (
                    f'Uploaded {file_type.title()} files remain comparison sources until '
                    'the complete STH validation passes; they do not currently replace '
                    'the calculator tables.'
                ),
            }

        if file_type == 'PRODUCTS':
            applied = next(
                (item for item in snapshots if self._has_active_product_apply(item)),
                None,
            )
            if applied:
                return {
                    'label': 'In use',
                    'tone': 'operational',
                    'detail': (
                        f'Applied from {applied.original_filename} on '
                        f'{applied.uploaded_at:%d %b %Y %H:%M}.'
                    ),
                }
            master = ProductMaster.objects.filter(status='VALIDATED').first()
            detail = 'The calculator uses the Product records already stored in the database.'
            if master:
                summary = master.validation_summary or {}
                rows = int(summary.get('rows_read', 0))
                omitted = int(summary.get('rows_omitted_without_customer', 0))
                detail += (
                    f' Company-wide Product Master validated: {rows:,} retained rows; '
                    f'{omitted:,} row(s) without CUSTOMER omitted. Linked STH rows are '
                    'available for controlled reconciliation.'
                )
            elif latest:
                detail += f' Latest received file: {latest.get_status_display()}.'
            return {
                'label': 'Operational baseline — master pending review',
                'tone': 'baseline',
                'detail': detail,
            }

        active = next((item for item in snapshots if item.status == 'ACTIVE'), None)
        if active:
            label = 'In use (add-only)' if file_type == 'SUBURBS' else 'In use'
            detail = (
                f'{active.original_filename}, activated '
                f'{active.activated_at:%d %b %Y %H:%M}.'
                if active.activated_at
                else f'{active.original_filename} is the active operational source.'
            )
            return {'label': label, 'tone': 'operational', 'detail': detail}

        detail = 'The calculator uses the records already stored in the database.'
        if latest:
            detail += f' Latest received file: {latest.get_status_display()}.'
        return {
            'label': 'Operational database (baseline)',
            'tone': 'baseline',
            'detail': detail,
        }

    @staticmethod
    def _ftp_file_status(filename, configurations):
        active_configurations = [item for item in configurations if item.active]
        if not active_configurations:
            return {
                'code': 'disabled',
                'label': 'Not scheduled',
                'detail': 'Enable this file in the FTP schedule before processing it.',
                'tone': 'muted',
                'can_process': False,
                'source_present': False,
                'source_size': 0,
                'seconds_remaining': 0,
            }

        source_path = ftp_uploaded_data_root() / filename
        try:
            source_stat = source_path.stat()
        except (FileNotFoundError, NotADirectoryError):
            return {
                'code': 'missing',
                'label': 'File not found',
                'detail': f'Upload the completed file using the exact filename {filename}.',
                'tone': 'warning',
                'can_process': False,
                'source_present': False,
                'source_size': 0,
                'seconds_remaining': 0,
            }
        except OSError as exc:
            return {
                'code': 'failed',
                'label': 'Inbox unavailable',
                'detail': f'The FTP inbox could not be read: {exc}',
                'tone': 'error',
                'can_process': False,
                'source_present': False,
                'source_size': 0,
                'seconds_remaining': 0,
            }

        if not source_path.is_file():
            return {
                'code': 'missing',
                'label': 'File not found',
                'detail': f'Upload the completed file using the exact filename {filename}.',
                'tone': 'warning',
                'can_process': False,
                'source_present': False,
                'source_size': 0,
                'seconds_remaining': 0,
            }

        minimum_age = max(
            item.minimum_file_age_seconds for item in active_configurations
        )
        modified_at = datetime.fromtimestamp(
            source_stat.st_mtime,
            tz=timezone.get_current_timezone(),
        )
        age_seconds = (timezone.now() - modified_at).total_seconds()
        seconds_remaining = max(0, ceil(minimum_age - age_seconds))
        common = {
            'source_present': True,
            'source_size': source_stat.st_size,
            'seconds_remaining': seconds_remaining,
        }

        if source_stat.st_size == 0:
            return {
                **common,
                'code': 'failed',
                'label': 'File is empty',
                'detail': 'Upload a complete, non-empty file before processing it.',
                'tone': 'error',
                'can_process': False,
            }

        if seconds_remaining:
            return {
                **common,
                'code': 'verifying',
                'label': 'Verifying upload',
                'detail': (
                    'Checking that the upload has finished. Ready in about '
                    f'{seconds_remaining} second(s). Do not process yet.'
                ),
                'tone': 'checking',
                'can_process': False,
            }

        all_checked_after_upload = all(
            item.last_checked_at and item.last_checked_at >= modified_at
            for item in active_configurations
        )
        statuses = {item.last_status for item in active_configurations}
        messages_for_status = [
            item.last_message.strip()
            for item in active_configurations
            if item.last_message.strip()
        ]

        if all_checked_after_upload and 'ERROR' in statuses:
            return {
                **common,
                'code': 'failed',
                'label': 'Processing failed',
                'detail': messages_for_status[0] if messages_for_status else 'Review the last FTP check and try again.',
                'tone': 'error',
                'can_process': True,
            }

        if all_checked_after_upload and statuses <= {'NEW_SNAPSHOT', 'UNCHANGED'}:
            unchanged = statuses == {'UNCHANGED'}
            return {
                **common,
                'code': 'completed',
                'label': 'Completed — unchanged' if unchanged else 'Completed',
                'detail': (
                    'This uploaded file was already processed; no new snapshot was needed.'
                    if unchanged else 'This uploaded file was processed successfully.'
                ),
                'tone': 'success',
                'can_process': True,
            }

        return {
            **common,
            'code': 'ready',
            'label': 'Ready to process',
            'detail': (
                f'Upload appears complete: the file has not changed for at least '
                f'{minimum_age} second(s). Size and date are checked again during processing.'
            ),
            'tone': 'ready',
            'can_process': True,
        }

    def _file_rows(self, request):
        clients = self._clients(request)
        ftp_root = ftp_uploaded_data_root()
        configurations = FtpImportConfiguration.objects.filter(client__in=clients)
        snapshots = ExternalDataFile.objects.filter(client__in=clients)
        rows = []
        for value, label in FTP_FILE_CHOICES:
            file_type, filename = value.split('|', 1)
            file_configurations = configurations.filter(
                file_type=file_type,
                filename=filename,
            )
            configuration_list = list(file_configurations)
            active_count = sum(item.active for item in configuration_list)
            latest_configuration = max(
                configuration_list,
                key=lambda item: (item.last_checked_at or item.updated_at, item.pk),
                default=None,
            )
            ftp_status = self._ftp_file_status(filename, configuration_list)
            file_snapshots = snapshots.filter(file_type=file_type).order_by(
                '-uploaded_at', '-pk',
            )
            latest_snapshot = file_snapshots.first()
            operational = self._operational_state(file_type, file_snapshots)
            global_master = None
            global_admin_name = ''
            if file_type == 'PRODUCTS':
                global_master = ProductMaster.objects.first()
                global_admin_name = 'imports_productmaster'
            elif file_type == 'STOCK':
                global_master = StockMaster.objects.first()
                global_admin_name = 'imports_stockmaster'
            rows.append({
                'file_type': file_type,
                'file_type_label': label.split(' — ', 1)[0],
                'filename': filename,
                'source_present': (ftp_root / filename).is_file(),
                'source_size': (
                    (ftp_root / filename).stat().st_size
                    if (ftp_root / filename).is_file() else 0
                ),
                'enabled': active_count > 0,
                'ftp_status': ftp_status,
                'active_client_count': active_count,
                'last_status': (
                    latest_configuration.get_last_status_display()
                    if latest_configuration else 'Never checked'
                ),
                'last_checked_at': (
                    latest_configuration.last_checked_at
                    if latest_configuration else None
                ),
                'last_message': (
                    latest_configuration.last_message
                    if latest_configuration else ''
                ),
                'latest_snapshot': latest_snapshot,
                'operational': operational,
                'upload_url': reverse(
                    'admin:imports_ftpimportschedule_upload_now',
                    args=[FTP_UPLOAD_KEY_BY_TYPE[file_type]],
                ),
                'status_url': reverse(
                    'admin:imports_ftpimportschedule_file_status',
                    args=[FTP_UPLOAD_KEY_BY_TYPE[file_type]],
                ),
                'history_url': (
                    reverse(f'admin:{global_admin_name}_changelist')
                    if global_master else (
                        reverse('admin:imports_externaldatafile_changelist')
                        + f'?file_type__exact={file_type}'
                    )
                ),
                'review_url': (
                    reverse(f'admin:{global_admin_name}_change', args=[global_master.pk])
                    if global_master else (reverse(
                        'admin:imports_externaldatafile_change',
                        args=[latest_snapshot.pk],
                    ) if latest_snapshot else '')
                ),
            })
        return rows

    def file_status_view(self, request, file_key):
        definition = FTP_UPLOAD_DEFINITIONS.get(file_key)
        if definition is None:
            raise Http404
        if not self._has_run_permission(request):
            raise PermissionDenied('Missing permission to view FTP import status.')

        configurations = list(FtpImportConfiguration.objects.filter(
            client__in=self._clients(request),
            file_type=definition['file_type'],
            filename=definition['filename'],
        ))
        return JsonResponse(
            self._ftp_file_status(definition['filename'], configurations)
        )

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        context = dict(extra_context or {})
        ftp_root = ftp_uploaded_data_root()
        context.update({
            'file_rows': self._file_rows(request),
            'recent_imports': ExternalDataFile.objects.filter(
                client__in=self._clients(request),
            ).select_related('client').order_by('-uploaded_at', '-pk')[:10],
            'check_inbox_url': reverse(
                'admin:imports_ftpimportschedule_check_inbox_now',
            ),
            'import_history_url': reverse('admin:imports_externaldatafile_changelist'),
            'title': 'Import Centre',
            'ftp_inbox_path': str(ftp_root),
            'ftp_inbox_available': ftp_root.exists() and ftp_root.is_dir(),
        })
        return super().changeform_view(
            request,
            object_id=object_id,
            form_url=form_url,
            extra_context=context,
        )

    @admin.display(description='Days')
    def selected_days(self, obj):
        labels = (
            ('monday', 'Mon'), ('tuesday', 'Tue'), ('wednesday', 'Wed'),
            ('thursday', 'Thu'), ('friday', 'Fri'), ('saturday', 'Sat'),
            ('sunday', 'Sun'),
        )
        return ', '.join(label for field, label in labels if getattr(obj, field))

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not FtpImportSchedule.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        selected = {
            tuple(value.split('|', 1))
            for value in form.cleaned_data.get('enabled_files', [])
        }
        clients = Client.objects.filter(active=True)
        configurations = FtpImportConfiguration.objects.filter(client__in=clients)
        configurations.update(active=False)

        for client in clients:
            for file_type, filename in selected:
                FtpImportConfiguration.objects.update_or_create(
                    client=client,
                    filename=filename,
                    defaults={
                        'file_type': file_type,
                        'active': True,
                    },
                )

        self.message_user(
            request,
            f'{len(selected)} file(s) selected for '
            f'{clients.count()} active client(s).',
            level=messages.SUCCESS,
        )

    def _has_run_permission(self, request):
        return request.user.is_superuser or request.user.has_perm(
            'imports.run_ftp_import_configuration'
        )

    @staticmethod
    def _result_messages(results):
        return list(dict.fromkeys(
            result['message'].strip()
            for result in results
            if result.get('message', '').strip()
            and result.get('status') in {'WAITING', 'ERROR'}
        ))

    @staticmethod
    def _retry_guidance(schedule):
        if schedule and schedule.active:
            return (
                f'Automatic checks will try again every {schedule.retry_minutes} minute(s) '
                'after the scheduled run time on enabled days. You can also use Process '
                'from FTP after correcting the problem.'
            )
        return (
            'Automatic checks are disabled. Correct the problem and use Process from FTP, '
            'or enable the schedule.'
        )

    def check_inbox_now_view(self, request):
        if request.method != 'POST':
            raise Http404
        if not self._has_run_permission(request):
            raise PermissionDenied('Missing permission to run FTP imports.')

        configurations = FtpImportConfiguration.objects.filter(
            client__in=self._clients(request),
            active=True,
        ).order_by('client__code', 'filename')
        totals = {
            'NEW_SNAPSHOT': 0,
            'UNCHANGED': 0,
            'WAITING': 0,
            'ERROR': 0,
            'SKIPPED': 0,
        }
        results = []
        for configuration in configurations:
            result = process_ftp_configuration(
                configuration.pk,
                actor=request.user,
                request=request,
                trigger='MANUAL',
                force=True,
            )
            results.append(result)
            totals[result['status']] = totals.get(result['status'], 0) + 1

        message = (
            f'FTP inbox check complete: {totals["NEW_SNAPSHOT"]} new snapshot(s), '
            f'{totals["UNCHANGED"]} unchanged, {totals["WAITING"]} waiting, '
            f'{totals["ERROR"]} error(s), {totals["SKIPPED"]} skipped. '
            'No operational data was activated.'
        )
        details = self._result_messages(results)
        if details:
            message = f'{message} {" ".join(details)}'
        if totals['WAITING'] or totals['ERROR']:
            schedule = FtpImportSchedule.objects.order_by('pk').first()
            message = f'{message} {self._retry_guidance(schedule)}'
        level = messages.WARNING if totals['WAITING'] or totals['ERROR'] else messages.SUCCESS
        self.message_user(request, message, level=level)
        schedule = FtpImportSchedule.objects.order_by('pk').first()
        return redirect('admin:imports_ftpimportschedule_change', schedule.pk)

    def upload_now_view(self, request, file_key):
        definition = FTP_UPLOAD_DEFINITIONS.get(file_key)
        if definition is None:
            raise Http404
        if not self._has_run_permission(request):
            raise PermissionDenied('Missing permission to run FTP imports.')

        configurations = FtpImportConfiguration.objects.filter(
            client__in=self._clients(request),
            active=True,
            file_type=definition['file_type'],
            filename=definition['filename'],
        ).order_by('client__code', 'pk')

        if request.method == 'POST':
            totals = {
                'NEW_SNAPSHOT': 0,
                'UNCHANGED': 0,
                'WAITING': 0,
                'ERROR': 0,
                'SKIPPED': 0,
            }
            results = []
            for configuration in configurations:
                result = process_ftp_configuration(
                    configuration.pk,
                    actor=request.user,
                    request=request,
                    trigger='MANUAL',
                    force=True,
                )
                results.append(result)
                totals[result['status']] = totals.get(result['status'], 0) + 1

            if not results:
                self.message_user(
                    request,
                    (
                        f'{definition["filename"]} is not enabled in the FTP schedule. '
                        'Enable it and save the schedule before processing it.'
                    ),
                    level=messages.WARNING,
                )
            else:
                details = self._result_messages(results)
                if totals['WAITING'] or totals['ERROR']:
                    completely_processed = totals['NEW_SNAPSHOT'] + totals['UNCHANGED']
                    if completely_processed:
                        message = (
                            f'{definition["filename"]} could not be processed for every '
                            'enabled mapping.'
                        )
                    else:
                        message = f'{definition["filename"]} was not imported.'
                    if details:
                        message = f'{message} {" ".join(details)}'
                    schedule = FtpImportSchedule.objects.order_by('pk').first()
                    message = f'{message} {self._retry_guidance(schedule)}'
                elif totals['NEW_SNAPSHOT']:
                    message = (
                        f'{definition["filename"]}: {totals["NEW_SNAPSHOT"]} new '
                        'snapshot(s) registered. No operational data was activated.'
                    )
                else:
                    message = (
                        f'{definition["filename"]} was found but is unchanged. '
                        'No new snapshot was created.'
                    )
                self.message_user(
                    request,
                    message,
                    level=(
                        messages.WARNING
                        if totals['WAITING'] or totals['ERROR']
                        else messages.SUCCESS
                    ),
                )

            successful = next(
                (result for result in results if result.get('external_file_id')),
                None,
            )
            if successful:
                if successful.get('product_master_id'):
                    schedule = FtpImportSchedule.objects.order_by('pk').first()
                    return redirect(
                        'admin:imports_ftpimportschedule_change',
                        schedule.pk,
                    )
                if successful.get('stock_master_id'):
                    return redirect(
                        'admin:imports_stockmaster_change',
                        successful['stock_master_id'],
                    )
                if len(results) == 1:
                    return redirect(
                        'admin:imports_externaldatafile_change',
                        successful['external_file_id'],
                    )

            schedule = FtpImportSchedule.objects.order_by('pk').first()
            return redirect('admin:imports_ftpimportschedule_change', schedule.pk)

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': f'Process from FTP — {definition["filename"]}',
            'filename': definition['filename'],
            'file_type': definition['file_type'],
            'is_enabled': configurations.exists(),
            'back_url': reverse('admin:imports_ftpimportschedule_changelist'),
        }
        return TemplateResponse(
            request,
            'admin/imports/ftpimportschedule/upload_now.html',
            context,
        )


@admin.register(FtpImportConfiguration)
class FtpImportConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        'client',
        'filename',
        'file_type',
        'active',
        'last_status',
        'last_checked_at',
        'snapshot_link',
    )
    list_filter = ('client', 'active', 'file_type', 'last_status')
    search_fields = ('client__code', 'client__name', 'filename', 'last_message')
    list_select_related = ('client', 'last_snapshot')
    ordering = ('client__code', 'filename')
    actions = ('run_selected_now',)
    readonly_fields = (
        'last_checked_at',
        'last_success_at',
        'last_status',
        'last_message',
        'last_snapshot',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        (
            'Source file',
            {
                'fields': ('client', 'file_type', 'filename', 'active'),
                'description': (
                    'The FTP service must deposit the completed file directly in uploaded_data. '
                    'For safe delivery, upload with a temporary name and rename it to this filename when complete.'
                ),
            },
        ),
        (
            'Schedule',
            {
                'fields': (
                    'minimum_file_age_seconds',
                ),
                'description': (
                    'All enabled client files use the one shared FTP schedule. '
                    'Minimum file age prevents reading a transfer that is still finishing.'
                ),
            },
        ),
        (
            'Last result',
            {
                'fields': (
                    'last_checked_at',
                    'last_success_at',
                    'last_status',
                    'last_message',
                    'last_snapshot',
                    'created_at',
                    'updated_at',
                ),
                'description': (
                    'Registration creates an immutable Django snapshot only. It does not activate or replace '
                    'operational Products, Fuel, Rates, Zones, Stock, or Suburbs.'
                ),
            },
        ),
    )

    def get_model_perms(self, request):
        """Keep the implementation detail out of the Admin index."""
        return {}

    def _clients(self, request):
        if request.user.is_superuser:
            return Client.objects.filter(active=True)
        try:
            return allowed_clients_for(request.user)
        except CalculatorAccessDenied:
            return Client.objects.none()

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(client__in=self._clients(request))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'client':
            kwargs['queryset'] = self._clients(request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not self._clients(request).filter(pk=obj.client_id).exists():
            raise PermissionDenied('This Client is not authorised for the current user.')
        super().save_model(request, obj, form, change)

    @admin.display(description='Snapshot')
    def snapshot_link(self, obj):
        if not obj.last_snapshot_id:
            return '—'
        url = reverse(
            'admin:imports_externaldatafile_change',
            args=[obj.last_snapshot_id],
        )
        return format_html('<a href="{}">#{}</a>', url, obj.last_snapshot_id)

    def has_run_ftp_import_configuration_permission(self, request):
        return request.user.is_superuser or request.user.has_perm(
            'imports.run_ftp_import_configuration'
        )

    @admin.action(
        description='Run all enabled FTP files now',
        permissions=['run_ftp_import_configuration'],
    )
    def run_selected_now(self, request, queryset):
        queryset = self.get_queryset(request).filter(active=True)
        totals = {
            'NEW_SNAPSHOT': 0,
            'UNCHANGED': 0,
            'WAITING': 0,
            'ERROR': 0,
            'SKIPPED': 0,
        }
        for configuration in queryset:
            result = process_ftp_configuration(
                configuration.pk,
                actor=request.user,
                request=request,
                trigger='MANUAL',
                force=True,
            )
            totals[result['status']] = totals.get(result['status'], 0) + 1

        message = (
            f'FTP run complete: {totals["NEW_SNAPSHOT"]} new snapshot(s), '
            f'{totals["UNCHANGED"]} unchanged, {totals["WAITING"]} waiting, '
            f'{totals["ERROR"]} error(s), {totals["SKIPPED"]} skipped. '
            'No operational data was activated.'
        )
        level = messages.WARNING if totals['WAITING'] or totals['ERROR'] else messages.SUCCESS
        self.message_user(request, message, level=level)
