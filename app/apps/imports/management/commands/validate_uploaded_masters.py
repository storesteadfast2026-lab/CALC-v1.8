from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from apps.imports.models import ProductMaster, StockMaster
from apps.imports.services.global_stock_master import validate_stock_master
from apps.imports.services.product_master import validate_product_master


class Command(BaseCommand):
    help = (
        'Preserve and validate the complete products.xls and stock.xls files '
        'from uploaded_data. This never applies operational Product changes.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--products', default='products.xls')
        parser.add_argument('--stock', default='stock.xls')

    def _source(self, filename):
        safe_name = Path(filename).name
        if safe_name != filename:
            raise CommandError('Master filenames must be simple names inside uploaded_data.')
        path = (Path(settings.BASE_DIR) / 'uploaded_data' / safe_name).resolve()
        expected_parent = (Path(settings.BASE_DIR) / 'uploaded_data').resolve()
        if path.parent != expected_parent or not path.is_file():
            raise CommandError(f'Master source not found: {path}')
        content = path.read_bytes()
        if not content:
            raise CommandError(f'Master source is empty: {path}')
        return path, content, sha256(content).hexdigest()

    def _product(self, filename):
        path, content, digest = self._source(filename)
        existing = ProductMaster.objects.filter(sha256=digest).order_by('-pk').first()
        if existing:
            self.stdout.write(
                f'Product Master #{existing.pk} already preserves {path.name}: {existing.status}'
            )
            return existing
        master = ProductMaster(
            original_filename=path.name,
            sha256=digest,
            file_size_bytes=len(content),
        )
        master.original_file.save(path.name, ContentFile(content), save=False)
        master.save()
        master = validate_product_master(master.pk)
        self.stdout.write(
            f'Product Master #{master.pk}: {master.status}; '
            f'rows={master.validation_summary.get("rows_read", 0)}'
        )
        if master.error_message:
            self.stdout.write(self.style.ERROR(master.error_message))
        return master

    def _stock(self, filename):
        path, content, digest = self._source(filename)
        existing = StockMaster.objects.filter(sha256=digest).order_by('-pk').first()
        if existing:
            self.stdout.write(
                f'Stock Master #{existing.pk} already preserves {path.name}: {existing.status}'
            )
            return existing
        master = StockMaster(
            original_filename=path.name,
            sha256=digest,
            file_size_bytes=len(content),
        )
        master.original_file.save(path.name, ContentFile(content), save=False)
        master.save()
        master = validate_stock_master(master.pk)
        self.stdout.write(
            f'Stock Master #{master.pk}: {master.status}; '
            f'rows={master.validation_summary.get("rows_read", 0)}; '
            f'valid={master.validation_summary.get("rows_valid", 0)}; '
            f'invalid={master.validation_summary.get("rows_invalid", 0)}'
        )
        if master.error_message:
            self.stdout.write(self.style.ERROR(master.error_message))
        return master

    def handle(self, *args, **options):
        product = self._product(options['products'])
        stock = self._stock(options['stock'])
        if product.status != 'VALIDATED' or stock.status != 'VALIDATED':
            raise CommandError('One or more master files failed validation; no operational data was applied.')
        self.stdout.write(self.style.SUCCESS(
            'Product and Stock masters validated. Operational Product data remains unchanged.'
        ))
