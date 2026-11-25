from django.test import TestCase

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
