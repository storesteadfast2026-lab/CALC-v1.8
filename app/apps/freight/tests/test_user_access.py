import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client as HttpClient, TestCase
from django.urls import reverse

from apps.authentication_gateway.models import CalculatorUserProfile
from apps.clients.models import Client, FreightCalculator
from apps.freight.services.dtos import FreightResult
from apps.products.models import Product


class FreightUserAccessTests(TestCase):
    def setUp(self):
        self.sth = Client.objects.create(code='STH', name='STH')
        self.other = Client.objects.create(code='OTHER', name='Other')
        self.User = get_user_model()

    def _customer(self):
        user = self.User.objects.create_user(
            username='customer@example.com',
            email='customer@example.com',
            password='test-pass',
        )
        CalculatorUserProfile.objects.create(
            user=user,
            role=CalculatorUserProfile.Role.CUSTOMER_USER,
            client_scope=CalculatorUserProfile.ClientScope.SINGLE_CLIENT,
            client=self.sth,
        )
        return user

    def _internal_selected(self):
        user = self.User.objects.create_user(
            username='internal@example.com',
            email='internal@example.com',
            password='test-pass',
        )
        profile = CalculatorUserProfile.objects.create(
            user=user,
            role=CalculatorUserProfile.Role.INTERNAL_USER,
            client_scope=CalculatorUserProfile.ClientScope.SELECTED_CLIENTS,
        )
        profile.allowed_clients.add(self.other)
        return user

    def test_anonymous_page_redirects_to_login(self):
        response = self.client.get(reverse('freight_calculator'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_anonymous_api_returns_json_401(self):
        response = self.client.get(reverse('product_autocomplete'))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error'], 'Authentication required.')

    def test_v1_accounts_match_calculator_access(self):
        url = reverse('freight_accounts_api_v1')
        self.assertEqual(self.client.get(url).status_code, 401)
        for user, account in (
            (self._customer(), self.sth),
            (self._internal_selected(), self.other),
        ):
            with self.subTest(role=user.calculator_profile.role):
                self.client.force_login(user)
                self.assertEqual(self.client.get(url).json(), {
                    'results': [{'code': account.code, 'name': account.name}],
                })
                self.assertEqual(self.client.post(url).status_code, 405)

    def test_v1_quote_enforces_session_csrf_and_account_access(self):
        url = reverse('quote_api_v1')
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {}).status_code, 401)

        browser = HttpClient(enforce_csrf_checks=True)
        browser.force_login(self._customer())
        page = browser.get(reverse('freight_calculator'))
        token = page.cookies['csrftoken'].value
        payload = {'client_code': self.other.code, 'lines': []}
        self.assertEqual(browser.post(url, payload, content_type='application/json').status_code, 403)
        response = browser.post(
            url, payload, content_type='application/json', HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'This user cannot access the requested client.')
        for invalid_payload in ('[]', '{"client_code": 42}', '{"lines": null}'):
            with self.subTest(payload=invalid_payload):
                response = browser.post(
                    url, invalid_payload, content_type='application/json', HTTP_X_CSRFTOKEN=token,
                )
                self.assertEqual(response.status_code, 400)

    def test_customer_page_uses_assigned_client(self):
        self.client.force_login(self._customer())
        response = self.client.get(reverse('freight_calculator'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['client'], self.sth)
        self.assertContains(response, 'Estimate status')
        self.assertContains(response, 'Provisional estimates use confirmed charges only.')

    def test_customer_cannot_switch_client_in_query_string(self):
        self.client.force_login(self._customer())
        response = self.client.get(reverse('freight_calculator'), {'client': 'OTHER'})
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_query_products_for_other_client(self):
        self.client.force_login(self._customer())
        response = self.client.get(reverse('product_autocomplete'), {'client': 'OTHER'})
        self.assertEqual(response.status_code, 403)

    @patch('apps.freight.views.FreightCalculatorService.calculate', return_value=[])
    def test_calculation_uses_server_authorized_client(self, mocked_calculate):
        self.client.force_login(self._customer())
        payload = {
            'client_code': 'STH',
            'suburb': 'Adelaide',
            'state': 'SA',
            'postcode': '5000',
            'lines': [],
        }
        response = self.client.post(
            reverse('calculate_freight'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        request_dto = mocked_calculate.call_args.args[0]
        self.assertEqual(request_dto.client_code, 'STH')

    @patch('apps.freight.views.FreightCalculatorService.calculate', return_value=[])
    def test_enabled_cubic_margin_accepts_any_whole_number_from_zero_to_twenty(self, mocked_calculate):
        FreightCalculator.objects.create(
            client=self.sth,
            name='Current calculator',
            cubic_margin_enabled=True,
            cubic_margin_options=[],
        )
        self.client.force_login(self._customer())

        response = self.client.post(
            reverse('calculate_freight'),
            data=json.dumps({
                'client_code': 'STH',
                'suburb': 'Adelaide',
                'state': 'SA',
                'postcode': '5000',
                'cubic_margin_percent': '7',
                'lines': [],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mocked_calculate.call_args.args[0].cubic_margin_percent,
            Decimal('7'),
        )

    def test_cubic_margin_rejects_decimal_or_out_of_range_values(self):
        FreightCalculator.objects.create(
            client=self.sth,
            name='Current calculator',
            cubic_margin_enabled=True,
        )
        self.client.force_login(self._customer())

        for value in ('1.5', '-1', '21'):
            with self.subTest(value=value):
                response = self.client.post(
                    reverse('calculate_freight'),
                    data=json.dumps({
                        'client_code': 'STH',
                        'cubic_margin_percent': value,
                        'lines': [],
                    }),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()['error'],
                    'Cubic Margin must be a whole number between 0 and 20.',
                )

    def test_calculation_rejects_tampered_client(self):
        self.client.force_login(self._customer())
        response = self.client.post(
            reverse('calculate_freight'),
            data=json.dumps({'client_code': 'OTHER', 'lines': []}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    @patch('apps.freight.views.FreightCalculatorService.calculate', return_value=[])
    def test_preselected_sku_uses_server_owned_physical_data(self, mocked_calculate):
        product = Product.objects.create(
            client=self.sth,
            sku='SAFE-1',
            freight_type='P',
            length_m='2.5',
            width_m='1.2',
            height_m='0.8',
            weight_kg='700',
            cubic_m3='2.4',
            active=True,
        )
        self.client.force_login(self._customer())

        response = self.client.post(
            reverse('calculate_freight'),
            data=json.dumps({
                'client_code': 'STH', 'suburb': 'Adelaide', 'state': 'SA',
                'postcode': '5000', 'preselect_sku': 'YES',
                'lines': [{
                    'product_id': product.pk,
                    'sku': product.sku,
                    'quantity': '2',
                    'freight_type': 'C',
                    'length_m': '99',
                    'width_m': '99',
                    'height_m': '99',
                    'weight_kg': '1',
                    'cubic_m3': '1',
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        request_line = mocked_calculate.call_args.args[0].lines[0]
        self.assertEqual(request_line.quantity, Decimal('2'))
        self.assertEqual(request_line.freight_type, 'P')
        self.assertEqual(request_line.length_m, Decimal('2.5000'))
        self.assertEqual(request_line.weight_kg, Decimal('700.0000'))
        self.assertEqual(request_line.cubic_m3, Decimal('2.400000'))

    def test_preselected_unknown_sku_is_rejected_without_product_id(self):
        self.client.force_login(self._customer())

        response = self.client.post(
            reverse('calculate_freight'),
            data=json.dumps({
                'client_code': 'STH', 'suburb': 'Adelaide', 'state': 'SA',
                'postcode': '5000', 'preselect_sku': 'YES',
                'lines': [{'sku': 'NOT-A-PRODUCT', 'quantity': '1'}],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    def test_preselected_product_with_large_dimension_difference_is_rejected(self):
        product = Product.objects.create(
            client=self.sth,
            sku='CHECK-VOLUME',
            freight_type='P',
            length_m='1.2',
            width_m='1.2',
            height_m='1.2',
            weight_kg='10',
            cubic_m3='0.0864',
            active=True,
        )
        self.client.force_login(self._customer())

        response = self.client.post(
            reverse('calculate_freight'),
            data=json.dumps({
                'client_code': 'STH', 'suburb': 'Adelaide', 'state': 'SA',
                'postcode': '5000', 'preselect_sku': 'YES',
                'lines': [{
                    'product_id': product.pk,
                    'sku': product.sku,
                    'quantity': '1',
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('need confirmation', response.json()['error'])

    def test_internal_user_can_use_selected_client(self):
        self.client.force_login(self._internal_selected())
        response = self.client.get(reverse('freight_calculator'), {'client': 'OTHER'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['client'], self.other)

    def _quoted_result(self):
        return FreightResult(
            carrier='KTI',
            service='GENERAL',
            estimate_ex_gst=Decimal('123.45'),
            status='L',
            details={
                'freight_base': '100.00',
                'fuel': '23.45',
                'operational_status': 'PROVISIONAL',
                'source_versions': {'operational_workbook': {'external_file_id': 8}},
            },
        )

    @patch('apps.freight.views.FreightCalculatorService.calculate')
    def test_customer_api_does_not_receive_internal_cost_details(self, mocked_calculate):
        mocked_calculate.return_value = [self._quoted_result()]
        self.client.force_login(self._customer())

        response = self.client.post(
            reverse('calculate_freight'),
            data=json.dumps({
                'client_code': 'STH', 'suburb': 'Adelaide', 'state': 'SA',
                'postcode': '5000', 'lines': [],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['details'], {})
        self.assertEqual(
            response.json()['results'][0]['quote_status'],
            'PROVISIONAL',
        )
        self.assertNotContains(response, 'freight_base')

    @patch('apps.freight.views.FreightCalculatorService.calculate')
    def test_internal_api_receives_breakdown_and_source_versions(self, mocked_calculate):
        mocked_calculate.return_value = [self._quoted_result()]
        self.client.force_login(self._internal_selected())

        response = self.client.post(
            reverse('calculate_freight'),
            data=json.dumps({
                'client_code': 'OTHER', 'suburb': 'Adelaide', 'state': 'SA',
                'postcode': '5000', 'lines': [],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        details = response.json()['results'][0]['details']
        self.assertEqual(details['freight_base'], '100.00')
        self.assertEqual(
            details['source_versions']['operational_workbook']['external_file_id'],
            8,
        )
