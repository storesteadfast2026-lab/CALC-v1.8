from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.imports.models import FtpImportConfiguration, FtpImportSchedule
from apps.imports.services.audit import create_audit_event
from apps.imports.services.ftp_inbox import (
    FtpInboxError,
    _create_snapshot,
    ftp_uploaded_data_root,
)
from apps.imports.services.product_master import register_product_master_snapshot
from apps.imports.services.global_stock_master import register_stock_master_snapshot


class FtpSourceWaiting(FtpInboxError):
    """The configured source is absent, empty, too new, or still changing."""


def configuration_is_due(
    configuration: FtpImportConfiguration,
    *,
    schedule: FtpImportSchedule | None = None,
    now=None,
) -> bool:
    """Return whether one enabled file is due under the shared schedule."""
    if not configuration.active:
        return False

    schedule = schedule or FtpImportSchedule.objects.first()
    if schedule is None or not schedule.active:
        return False

    now = now or timezone.now()
    schedule_timezone = timezone.get_default_timezone()
    local_now = timezone.localtime(now, schedule_timezone)
    if not getattr(schedule, schedule.WEEKDAY_FIELDS[local_now.weekday()]):
        return False
    if local_now.time().replace(tzinfo=None) < schedule.run_time:
        return False
    starts_at = schedule.starts_at
    if starts_at and now < starts_at:
        return False

    # Attempts before the new schedule started do not count towards its first run.
    first_run_day = (
        starts_at is not None
        and timezone.localdate(starts_at, schedule_timezone) == local_now.date()
    )

    if configuration.last_success_at:
        success_date = timezone.localdate(configuration.last_success_at, schedule_timezone)
        if success_date == local_now.date() and (
            not first_run_day or configuration.last_success_at >= starts_at
        ):
            return False

    if configuration.last_checked_at and (
        not first_run_day or configuration.last_checked_at >= starts_at
    ):
        retry_at = configuration.last_checked_at + timedelta(
            minutes=schedule.retry_minutes
        )
        if now < retry_at:
            return False
    return True


def _read_configured_source(configuration: FtpImportConfiguration, *, now):
    filename = str(configuration.filename or '').strip()
    if not filename or Path(filename).name != filename or filename in {'.', '..'}:
        raise FtpInboxError('Configured FTP filename must be a simple filename.')

    root = ftp_uploaded_data_root()
    if not root.exists() or not root.is_dir():
        raise FtpSourceWaiting(
            'FTP inbox is unavailable because its configured folder does not exist.'
        )

    source_path = (root / filename).resolve()
    if source_path.parent != root:
        raise FtpInboxError('Configured FTP source must be directly inside the FTP inbox.')
    if not source_path.exists() or not source_path.is_file():
        raise FtpSourceWaiting(
            f'File not found: {filename}. Upload the completed file to the FTP inbox '
            'using this exact filename.'
        )

    before = source_path.stat()
    modified_at = datetime.fromtimestamp(
        before.st_mtime,
        tz=timezone.get_current_timezone(),
    )
    age_seconds = (now - modified_at).total_seconds()
    if age_seconds < configuration.minimum_file_age_seconds:
        remaining = max(
            1,
            int(configuration.minimum_file_age_seconds - age_seconds),
        )
        raise FtpSourceWaiting(
            f'{filename} was found but may still be transferring. Try again in about '
            f'{remaining} second(s).'
        )

    content = source_path.read_bytes()
    after = source_path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise FtpSourceWaiting(
            f'{filename} changed while it was being read. It will be retried automatically.'
        )
    if not content:
        raise FtpSourceWaiting(
            f'{filename} was found but is empty. Upload a complete, non-empty file '
            'using this exact filename.'
        )
    return source_path, content, modified_at


def _save_result(
    configuration,
    *,
    now,
    status,
    message,
    success=False,
    external_file=None,
):
    configuration.last_checked_at = now
    configuration.last_status = status
    configuration.last_message = message
    fields = ['last_checked_at', 'last_status', 'last_message', 'updated_at']
    if success:
        configuration.last_success_at = now
        fields.append('last_success_at')
    if external_file is not None:
        configuration.last_snapshot = external_file
        fields.append('last_snapshot')
    configuration.save(update_fields=fields)


@transaction.atomic
def process_ftp_configuration(
    configuration_or_id,
    *,
    actor=None,
    request=None,
    trigger='MANUAL',
    force=False,
    now=None,
) -> dict:
    """Register one immutable FTP snapshot without activating operational data."""
    configuration_id = (
        configuration_or_id.pk
        if isinstance(configuration_or_id, FtpImportConfiguration)
        else int(configuration_or_id)
    )
    configuration = (
        FtpImportConfiguration.objects.select_for_update()
        .select_related('client')
        .get(pk=configuration_id)
    )
    now = now or timezone.now()

    if not configuration.active:
        return {
            'configuration_id': configuration.pk,
            'status': 'SKIPPED',
            'message': 'Configuration is inactive.',
            'processed': False,
        }
    if trigger == 'AUTOMATIC' and not force and not configuration_is_due(
        configuration,
        now=now,
    ):
        return {
            'configuration_id': configuration.pk,
            'status': 'SKIPPED',
            'message': 'Configuration is not due.',
            'processed': False,
        }

    try:
        source_path, content, modified_at = _read_configured_source(
            configuration,
            now=now,
        )
        external_file, created = _create_snapshot(
            client=configuration.client,
            file_type=configuration.file_type,
            source_path=source_path,
            content=content,
            actor=actor,
        )
        product_master = None
        stock_master = None
        if configuration.file_type == 'PRODUCTS':
            product_master, _master_created = register_product_master_snapshot(
                content,
                source_path.name,
                actor=actor,
            )
        elif configuration.file_type == 'STOCK':
            stock_master, _master_created = register_stock_master_snapshot(
                content,
                source_path.name,
                actor=actor,
            )
        status = 'NEW_SNAPSHOT' if created else 'UNCHANGED'
        message = (
            f'Snapshot #{external_file.pk} registered from {source_path.name}.'
            if created
            else f'{source_path.name} is unchanged; snapshot #{external_file.pk} already exists.'
        )
        _save_result(
            configuration,
            now=now,
            status=status,
            message=message,
            success=True,
            external_file=external_file,
        )
        create_audit_event(
            event_type=(
                'FTP_SCHEDULED_FILE_REGISTERED'
                if created
                else 'FTP_SCHEDULED_FILE_UNCHANGED'
            ),
            message=(
                f'{trigger.title()} FTP import for {configuration.client.code}: {message}'
            ),
            actor=actor,
            client=configuration.client,
            external_file=external_file,
            metadata={
                'configuration_id': configuration.pk,
                'trigger': trigger,
                'filename': source_path.name,
                'file_type': configuration.file_type,
                'source_modified_at': modified_at.isoformat(),
                'sha256': external_file.sha256,
                'new_snapshot': created,
                'product_master_id': product_master.pk if product_master else None,
                'stock_master_id': stock_master.pk if stock_master else None,
                'operational_data_changed': False,
            },
            request=request,
        )
        return {
            'configuration_id': configuration.pk,
            'status': status,
            'message': message,
            'processed': True,
            'new_snapshot': created,
            'external_file_id': external_file.pk,
            'product_master_id': product_master.pk if product_master else None,
            'stock_master_id': stock_master.pk if stock_master else None,
        }
    except FtpSourceWaiting as exc:
        message = str(exc)
        _save_result(
            configuration,
            now=now,
            status='WAITING',
            message=message,
        )
        create_audit_event(
            event_type='FTP_SCHEDULED_FILE_WAITING',
            message=message,
            actor=actor,
            client=configuration.client,
            severity='WARNING',
            metadata={
                'configuration_id': configuration.pk,
                'trigger': trigger,
                'filename': configuration.filename,
                'file_type': configuration.file_type,
                'operational_data_changed': False,
            },
            request=request,
        )
        return {
            'configuration_id': configuration.pk,
            'status': 'WAITING',
            'message': message,
            'processed': True,
        }
    except Exception as exc:
        message = str(exc)
        _save_result(
            configuration,
            now=now,
            status='ERROR',
            message=message,
        )
        create_audit_event(
            event_type='FTP_SCHEDULED_FILE_ERROR',
            message=message,
            actor=actor,
            client=configuration.client,
            severity='ERROR',
            metadata={
                'configuration_id': configuration.pk,
                'trigger': trigger,
                'filename': configuration.filename,
                'file_type': configuration.file_type,
                'operational_data_changed': False,
            },
            request=request,
        )
        return {
            'configuration_id': configuration.pk,
            'status': 'ERROR',
            'message': message,
            'processed': True,
        }


def process_due_ftp_configurations(*, now=None) -> dict:
    """Process all enabled client/file mappings under the shared schedule."""
    now = now or timezone.now()
    schedule = FtpImportSchedule.objects.first()
    configuration_ids = list(
        FtpImportConfiguration.objects.filter(
            active=True,
        ).values_list('pk', flat=True)
    )
    results = [
        process_ftp_configuration(
            configuration_id,
            trigger='AUTOMATIC',
            now=now,
        )
        for configuration_id in configuration_ids
    ]
    processed = [item for item in results if item['processed']]
    return {
        'configured': len(configuration_ids),
        'schedule_configured': schedule is not None,
        'processed': len(processed),
        'new_snapshots': sum(item.get('new_snapshot', False) for item in processed),
        'unchanged': sum(item['status'] == 'UNCHANGED' for item in processed),
        'waiting': sum(item['status'] == 'WAITING' for item in processed),
        'errors': sum(item['status'] == 'ERROR' for item in processed),
        'skipped': sum(item['status'] == 'SKIPPED' for item in results),
        'results': results,
    }
