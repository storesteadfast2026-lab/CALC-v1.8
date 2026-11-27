from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.clients.models import Client, FreightCalculator


class FreightCalculatorOptionsTests(TestCase):
    def test_cubic_margin_options_are_normalised_and_include_zero(self):
        client = Client.objects.create(code='STH', name='STH')
        calculator = FreightCalculator.objects.create(
            client=client,
            name='Freight Calculator',
            cubic_margin_options=[20, '10', -1, 101, 'bad', 10],
        )

        self.assertEqual(calculator.allowed_cubic_margins(), [0, 10, 20])

    def test_client_can_keep_an_archive_but_only_one_current_calculator(self):
        client = Client.objects.create(code='STH', name='STH')
        archived = FreightCalculator.objects.create(
            client=client,
            name='Freight Calculator',
            version='1.8',
            cubic_margin_options=[0, 5, 10, 15, 20],
            archived_at=timezone.now(),
        )
        FreightCalculator.objects.create(client=client, name='STH Freight Calculator', version='V2026.R2')

        with self.assertRaises(IntegrityError), transaction.atomic():
            FreightCalculator.objects.create(client=client, name='Another calculator', active=False)

        archived.refresh_from_db()
        self.assertEqual(archived.cubic_margin_options, [0, 5, 10, 15, 20])
