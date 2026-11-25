from decimal import Decimal

from django.test import SimpleTestCase

from apps.freight.services.operational_test_runner import (
    DispatchCase,
    _finalise_case,
    _select_unique_destinations,
)


def _case(row, suburb, state):
    return DispatchCase(
        source_row=row,
        client='STH',
        suburb=suburb,
        state=state,
        historical_zone='',
        historical_carrier='',
        historical_service='',
        job_number=str(row),
        quantity=Decimal('1'),
        pallets=Decimal('1'),
        weight_kg=Decimal('100'),
        cubic_m3=Decimal('1'),
        tailgate=False,
    )


class OperationalTestSelectionTests(SimpleTestCase):
    def test_selects_unique_destinations_in_state_round_robin(self):
        rows = [
            _case(2, 'ADELAIDE', 'SA'),
            _case(3, 'SYDNEY', 'NSW'),
            _case(4, 'ADELAIDE', 'SA'),
            _case(5, 'MELBOURNE', 'VIC'),
            _case(6, 'BANKSTOWN', 'NSW'),
        ]

        selected = _select_unique_destinations(rows, 4)

        self.assertEqual(
            [(item.suburb, item.state) for item in selected],
            [
                ('BANKSTOWN', 'NSW'),
                ('ADELAIDE', 'SA'),
                ('MELBOURNE', 'VIC'),
                ('SYDNEY', 'NSW'),
            ],
        )
        self.assertEqual(selected[1].source_row, 2)


class OperationalTestClassificationTests(SimpleTestCase):
    def _report_case(self, results=None, warnings=None, checks=None, **finalise_options):
        case = {
            'results': results or [],
            'warnings': warnings or [],
            'checks': checks or [],
        }
        _finalise_case(case, **finalise_options)
        return case

    def test_classifies_complete_quote_independently_from_review_warnings(self):
        case = self._report_case(
            results=[{'operational_status': 'COMPLETE'}],
            warnings=[{'status': 'NO_QUOTE'}],
        )

        self.assertEqual(case['outcome'], 'QUOTED_COMPLETE')
        self.assertTrue(case['review_required'])

    def test_classifies_provisional_only_quote(self):
        case = self._report_case(results=[{'operational_status': 'PROVISIONAL'}])

        self.assertEqual(case['outcome'], 'QUOTED_PROVISIONAL')
        self.assertTrue(case['review_required'])

    def test_classifies_no_quote_separately_from_failure(self):
        case = self._report_case(
            checks=[{'name': 'RESULT_AVAILABLE', 'passed': False, 'detail': 'No results.'}]
        )

        self.assertEqual(case['outcome'], 'NOT_QUOTED')
        self.assertTrue(case['review_required'])

    def test_classifies_execution_or_invariant_failure(self):
        case = self._report_case(execution_failed=True)

        self.assertEqual(case['outcome'], 'FAILED')
