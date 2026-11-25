from django.test import SimpleTestCase

from apps.imports.services.ratecard_chain import SUPPORTED_ROOTS
from apps.imports.services.ratecard_operational import build_operational_gate


def valid_report():
    return {
        'rates': {'missing_reference_details': []},
        'carriers': {
            carrier: {
                'rows': 1,
                'zones_in_csv': 1,
                'conflicts_with_postcode': [],
                'case_status': {'APPLICABLE': 2},
            }
            for carrier in SUPPORTED_ROOTS
        },
    }


class OperationalGateTests(SimpleTestCase):
    def test_rate_value_changes_are_explicitly_allowed(self):
        report = valid_report()
        report['carriers']['TEAMEX']['percent_of_price_lines'] = [
            {'card': 1, 'name': 'Fuel', 'rate': 999.99},
        ]

        gate = build_operational_gate(report)

        self.assertEqual(gate['status'], 'PASSED')
        self.assertTrue(gate['activation_allowed'])
        self.assertFalse(gate['compares_rate_values'])
        self.assertTrue(gate['rate_value_changes_allowed'])

    def test_other_customer_and_unreachable_cards_do_not_block_sth(self):
        report = valid_report()
        report['rates']['missing_reference_details'] = [
            {'card': 10, 'review_status': 'OTHER_CUSTOMER_ONLY', 'reachable_carriers': []},
            {'card': 11, 'review_status': 'UNREACHABLE_FROM_STH_ROOTS', 'reachable_carriers': []},
        ]

        self.assertEqual(build_operational_gate(report)['status'], 'PASSED')

    def test_reachable_missing_card_and_unknown_route_are_warnings(self):
        report = valid_report()
        report['rates']['missing_reference_details'] = [{
            'card': 1524,
            'review_status': 'SOURCE_FIELD_REQUIRED',
            'reachable_carriers': ['TEAMEX'],
        }]
        report['carriers']['TEAMEX']['case_status']['UNKNOWN'] = 3

        gate = build_operational_gate(report)

        self.assertEqual(gate['status'], 'PASSED')
        self.assertTrue(gate['activation_allowed'])
        self.assertEqual(gate['blockers'], [])
        self.assertEqual(
            [item['code'] for item in gate['warnings']],
            ['MISSING_RATE_CARD', 'UNRESOLVED_STH_ROUTE'],
        )

    def test_missing_carrier_blocks_but_conflicting_destination_is_a_warning(self):
        report = valid_report()
        report['carriers'].pop('STEA')
        report['carriers']['KTI']['conflicts_with_postcode'] = [['NAMBOUR', 'QLD', '4560']]
        report['carriers']['KTI']['conflict_details'] = [{
            'suburb': 'NAMBOUR', 'state': 'QLD', 'postcode': '4560',
            'zones': ['QL2', 'QLS'], 'rows': [183603, 183604],
        }]

        gate = build_operational_gate(report)
        codes = [item['code'] for item in gate['blockers']]

        self.assertIn('CARRIER_ZONES_MISSING', codes)
        self.assertNotIn('AMBIGUOUS_DESTINATION', codes)
        conflict = next(item for item in gate['warnings']
                        if item['code'] == 'AMBIGUOUS_DESTINATION')
        self.assertIn('NAMBOUR, QLD 4560 -> QL2, QLS (CSV rows 183603, 183604)',
                      conflict['detail'])
        self.assertIn('Contact Steadfast Customer Service by phone', conflict['detail'])

    def test_conflicting_destination_alone_does_not_block_activation(self):
        report = valid_report()
        report['carriers']['TFMX']['conflicts_with_postcode'] = [['RAVENHALL', 'VIC', '3023']]
        report['carriers']['TFMX']['conflict_details'] = [{
            'suburb': 'RAVENHALL', 'state': 'VIC', 'postcode': '3023',
            'zones': ['MEL', 'VDC'], 'rows': [191489, 191490],
        }]

        gate = build_operational_gate(report)

        self.assertEqual(gate['status'], 'PASSED')
        self.assertTrue(gate['activation_allowed'])
        self.assertEqual(gate['blockers'], [])
        self.assertEqual(gate['warnings'][0]['code'], 'AMBIGUOUS_DESTINATION')
