from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from apps.authentication_gateway.models import CalculatorUserProfile
from apps.clients.models import Client
from apps.locations.models import Suburb
from apps.products.models import Product


class CalculatorVisualContractTests(TestCase):
    """Protect the existing calculator contract during visual-only changes."""

    def setUp(self):
        self.client_record = Client.objects.create(code='STH', name='Steadfast')
        self.user = get_user_model().objects.create_user(
            username='customer@example.com',
            email='customer@example.com',
            password='test-pass',
        )
        CalculatorUserProfile.objects.create(
            user=self.user,
            role=CalculatorUserProfile.Role.CUSTOMER_USER,
            client_scope=CalculatorUserProfile.ClientScope.SINGLE_CLIENT,
            client=self.client_record,
        )
        self.client.force_login(self.user)

    def test_visual_layout_keeps_existing_dom_contract(self):
        response = self.client.get(reverse('freight_calculator'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="calculator-page"')
        self.assertContains(response, 'class="fc-workspace"')
        self.assertContains(response, 'Shipment summary')
        self.assertContains(response, 'class="fc-version"')
        self.assertContains(response, settings.APP_VERSION)
        self.assertNotContains(response, 'CAN_VIEW_QUOTE_DETAILS')
        self.assertNotContains(response, 'Operational source')
        self.assertNotContains(response, 'Base freight')

        required_ids = (
            'from_address_id',
            'suburb_search',
            'suburb_results',
            'destination_suburb',
            'state',
            'postcode',
            'tailgate',
            'preselect_sku',
            'cubic_margin_percent',
            'cubic_margin_preview',
            'lines',
            'item_count',
            'total_weight',
            'total_cubic',
            'calc_status',
            'error',
            'results',
        )
        for element_id in required_ids:
            self.assertContains(response, f'id="{element_id}"', count=1)

        self.assertContains(response, 'placeholder="Enter 0–20"')
        self.assertContains(response, 'Original 0.000 m³ → adjusted 0.000 m³')

    def test_destination_uses_one_visible_selector_and_hidden_components(self):
        response = self.client.get(reverse('freight_calculator'))

        self.assertContains(response, '<span class="field-label">To Suburb</span>')
        self.assertContains(response, '<input id="destination_suburb" type="hidden">')
        self.assertContains(response, '<input id="state" type="hidden">')
        self.assertContains(response, '<input id="postcode" type="hidden">')
        self.assertNotContains(response, '<span class="field-label">State</span>')
        self.assertNotContains(response, '<span class="field-label">Postcode</span>')
        self.assertContains(response, 'suburb:destinationSuburbInput.value')
        self.assertContains(response, 'state:destinationStateInput.value')
        self.assertContains(response, 'postcode:destinationPostcodeInput.value')

    def test_suburb_autocomplete_returns_full_label_and_separate_values(self):
        Suburb.objects.create(
            suburb_name='ADELAIDE',
            state='SA',
            postcode='5000',
        )

        response = self.client.get(reverse('suburb_autocomplete'), {'q': 'Adelaide'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [{
            'id': Suburb.objects.get().id,
            'label': 'ADELAIDE, SA 5000',
            'suburb': 'ADELAIDE',
            'state': 'SA',
            'postcode': '5000',
        }])

    def test_visual_layout_keeps_current_actions_without_unimplemented_controls(self):
        response = self.client.get(reverse('freight_calculator'))

        self.assertContains(response, 'onclick="addLine()"')
        self.assertContains(response, 'class="trash-icon"')
        self.assertContains(response, 'aria-label="Remove freight item"')
        self.assertContains(response, 'onclick="calculate()"')
        self.assertContains(response, "fetch('/api/calculate/'")
        self.assertNotContains(response, 'Save this shipment')
        self.assertNotContains(response, 'Where it&#x27;s going')
        self.assertNotContains(response, 'View and choose')

    @patch('apps.freight.views.product_contact_notices')
    def test_unknown_dimension_product_directs_user_to_customer_service(self, notices):
        notices.return_value = [{
            'sku': 'BRH4443',
            'name': 'Blocked Product',
            'description': '',
            'message': (
                'Dimensions are unavailable for this product. '
                'For an accurate quote, please call Steadfast Contact Center or Customer Service.'
            ),
        }]

        response = self.client.get(
            reverse('product_autocomplete'),
            {'client': 'STH', 'q': 'BRH4443'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [{
            'id': None,
            'sku': 'BRH4443',
            'label': 'BRH4443 — Call Steadfast Contact Center / Customer Service',
            'available': False,
            'message': (
                'Dimensions are unavailable for this product. '
                'For an accurate quote, please call Steadfast Contact Center or Customer Service.'
            ),
        }])

        page = self.client.get(reverse('freight_calculator'))
        self.assertContains(page, 'pickUnavailableProduct')
        self.assertContains(page, "tr.dataset.productUnavailable='true'")

    @patch('apps.freight.views.product_contact_notices', return_value=[])
    def test_active_product_with_large_dimension_difference_is_not_quotable(
        self, _notices,
    ):
        Product.objects.create(
            client=self.client_record,
            sku='CHECK-VOLUME',
            length_m='1.2',
            width_m='1.2',
            height_m='1.2',
            weight_kg='10',
            cubic_m3='0.0864',
            active=True,
        )

        response = self.client.get(
            reverse('product_autocomplete'),
            {'client': 'STH', 'q': 'CHECK-VOLUME'},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()['results'][0]
        self.assertIsNone(result['id'])
        self.assertFalse(result['available'])
        self.assertIn('need confirmation', result['message'])
