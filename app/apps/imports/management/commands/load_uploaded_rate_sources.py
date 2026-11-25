from django.core.management.base import BaseCommand, CommandError

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client
from apps.imports.models import ExternalDataFile
from apps.imports.services.ftp_inbox import scan_ftp_inbox
from apps.imports.services.rate_source_load import (
    RateSourceError,
    load_source,
    prepare_source,
)


# These are the six carrier/service paths demonstrated by the read-only STH
# analysis.  Keep the values local: the experimental route walker is
# deliberately isolated from every command that touches the ORM.
DEMONSTRATED_PATHS = (
    ('TEAMEX', 'ROAD'),
    ('KTI', 'GENERAL'),
    ('TFMX', 'ROAD'),
    ('TEAMTAS', 'GENERAL'),
    ('COCHRN', 'ROAD'),
    ('STEA', 'ROAD'),
)


class Command(BaseCommand):
    help = (
        'Register the demonstrated STH carrier/service paths as inactive, then '
        'version and load rates_all.xls and zones.csv for comparison. Quotes remain unchanged.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--client', default='STH')

    def _ensure_inactive_paths(self, client):
        created = 0
        for carrier_code, service_code in DEMONSTRATED_PATHS:
            carrier, _ = Carrier.objects.get_or_create(
                code=carrier_code,
                defaults={'name': carrier_code, 'active': True},
            )
            service, _ = CarrierService.objects.get_or_create(
                carrier=carrier,
                service_code=service_code,
                defaults={'service_name': service_code, 'active': True},
            )
            _, was_created = ClientCarrierConfig.objects.get_or_create(
                client=client,
                carrier_service=service,
                defaults={
                    'customer_code': client.code,
                    'ratecard': '',
                    'base_status': 'X',
                    'active': False,
                },
            )
            created += int(was_created)
        return created

    def _load_latest(self, client, file_type):
        source = ExternalDataFile.objects.filter(
            client=client,
            file_type=file_type,
            source_method='FTP_DROP',
        ).order_by('-uploaded_at', '-pk').first()
        if source is None:
            raise CommandError(f'No uploaded_data snapshot found for {file_type}.')
        if source.status == 'ACTIVE':
            self.stdout.write(
                f'{file_type} source #{source.pk} is already loaded; '
                f'rows={source.import_summary.get("rows_loaded", 0)}.'
            )
            return source
        try:
            preview = prepare_source(source)
            if source.status != 'VALIDATED':
                raise RateSourceError(source.error_message or f'{file_type} validation failed.')
            summary = load_source(source)
        except RateSourceError as exc:
            raise CommandError(f'{file_type}: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(
            f'{file_type} source #{source.pk} loaded for comparison; '
            f'rows={summary["rows_loaded"]}; quotes_changed={summary["quotes_changed"]}.'
        ))
        if file_type == 'RATES':
            missing = preview.get('load_preview', {}).get('missing_references', [])
            self.stdout.write(f'Missing Rate Card references retained for review: {len(missing)}')
        return source

    def handle(self, *args, **options):
        code = options['client'].strip().upper()
        try:
            client = Client.objects.get(code=code, active=True)
        except Client.DoesNotExist as exc:
            raise CommandError(f'Active Calculator Customer not found: {code}') from exc

        created = self._ensure_inactive_paths(client)
        self.stdout.write(
            f'Demonstrated carrier/service paths available: {len(DEMONSTRATED_PATHS)}; '
            f'new inactive configurations: {created}.'
        )
        scan = scan_ftp_inbox(client=client)
        self.stdout.write(
            f'uploaded_data scan: recognised={scan["recognised"]}; '
            f'new_snapshots={scan["new_snapshots"]}; errors={scan["errors"]}.'
        )
        self._load_latest(client, 'RATES')
        self._load_latest(client, 'ZONES')
