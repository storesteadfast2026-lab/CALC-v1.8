from django.core.management.base import BaseCommand, CommandError

from apps.clients.models import Client
from apps.imports.models import ExternalDataFile
from apps.imports.management.commands.validate_sth_rate_sources import validate_sources
from apps.imports.services.rate_source_load import read_source_bytes
from apps.imports.services.ratecard_operational import activate_operational_pair, build_operational_gate


class Command(BaseCommand):
    help = 'Activate the latest loaded STH Rates/Zones pair for complete operational quotes.'

    def handle(self, *args, **options):
        try:
            client = Client.objects.get(code__iexact='STH')
        except Client.DoesNotExist as exc:
            raise CommandError('STH client was not found.') from exc
        sources = {}
        for file_type in ('RATES', 'ZONES'):
            sources[file_type] = (
                ExternalDataFile.objects.filter(
                    client=client, file_type=file_type, status='ACTIVE',
                ).order_by('-activated_at', '-pk').first()
            )
            if sources[file_type] is None:
                raise CommandError(f'No active STH {file_type} source was found.')
        report = validate_sources(
            read_source_bytes(sources['RATES']), read_source_bytes(sources['ZONES']),
            sources['RATES'].original_filename,
        )
        gate = build_operational_gate(report)
        try:
            activate_operational_pair(sources['RATES'], sources['ZONES'], gate)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Enabled STH Rates #{sources['RATES'].pk} and Zones #{sources['ZONES'].pk}; "
            f"{len(gate['warnings'])} warning(s), COMPLETE paths only."
        ))
