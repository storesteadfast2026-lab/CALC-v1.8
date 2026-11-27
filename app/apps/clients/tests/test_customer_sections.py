from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.clients.models import Customer, Client, CommercialCustomer, CustomerSection


class CustomerSectionsTests(TestCase):
    def make_customer(self, code, row):
        return Customer.objects.create(code=code, name=code, source_row_number=row)

    def test_two_sections_one_customer_without_calculator(self):
        commercial = CommercialCustomer.objects.create(code='PON', name='PON')
        a = self.make_customer('PON', 1)
        b = self.make_customer('PBP', 2)
        CustomerSection.objects.create(commercial_customer=commercial, source_customer=a)
        CustomerSection.objects.create(commercial_customer=commercial, source_customer=b)
        self.assertEqual(commercial.sections.count(), 2)
        self.assertEqual(Client.objects.count(), 0)
        self.assertIsNone(a.linked_client_id)

    def test_a_section_cannot_belong_to_two_commercial_customers(self):
        source = self.make_customer('PBP', 1)
        first = CommercialCustomer.objects.create(code='PON', name='PON')
        second = CommercialCustomer.objects.create(code='OTHER', name='Other')
        CustomerSection.objects.create(commercial_customer=first, source_customer=source)
        with self.assertRaises(ValidationError):
            CustomerSection.objects.create(commercial_customer=second, source_customer=source)

    def test_special_customer_cannot_be_section(self):
        source = Customer.objects.create(code='*', name='Special', is_special=True, source_row_number=1)
        commercial = CommercialCustomer.objects.create(code='PON', name='PON')
        with self.assertRaises(ValidationError):
            CustomerSection.objects.create(commercial_customer=commercial, source_customer=source)


class CommercialCustomerAdminTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser('admin', 'admin@example.com'))
        self.commercial = CommercialCustomer.objects.create(code='ABC', name='Example company')
        self.abc = Customer.objects.create(code='ABC', name='Original account', source_row_number=1)
        self.ccs = Customer.objects.create(code='CCS', name='Second account', source_row_number=2)
        CustomerSection.objects.create(commercial_customer=self.commercial, source_customer=self.abc)
        self.change_url = reverse('admin:clients_commercialcustomer_change', args=[self.commercial.pk])
        self.search_url = reverse('admin:clients_commercialcustomer_code_search')

    def test_search_and_save_code_with_commercial_customer(self):
        response = self.client.get(self.change_url)
        self.assertContains(response, 'Original account')
        self.assertContains(response, self.search_url)
        self.assertContains(response, 'name="_save"', count=1)
        self.assertNotContains(response, 'name="_continue"')
        self.assertNotContains(response, 'name="_addanother"')

        response = self.client.get(self.search_url, {'term': 'Second account'})
        self.assertEqual(response.json()['results'], [{'id': str(self.ccs.pk), 'text': str(self.ccs)}])

        response = self.client.post(self.change_url, {
            'code': 'ABC', 'name': 'Updated company', 'customer_codes_to_add': [self.ccs.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.commercial.refresh_from_db()
        self.assertEqual(self.commercial.name, 'Updated company')
        self.assertQuerySetEqual(self.commercial.sections.values_list('source_customer__code', flat=True), ['ABC', 'CCS'])
        self.assertContains(self.client.get(self.change_url), 'Second account')

    def test_code_linked_elsewhere_cannot_be_selected_or_saved(self):
        other = CommercialCustomer.objects.create(code='OTHER', name='Other company')
        section = CustomerSection.objects.create(commercial_customer=other, source_customer=self.ccs)

        response = self.client.get(self.search_url, {'term': 'CCS'})
        self.assertEqual(response.json()['results'], [{
            'id': str(self.ccs.pk), 'text': f'{self.ccs} (linked to OTHER)', 'disabled': True,
        }])

        response = self.client.post(self.change_url, {
            'code': 'ABC', 'name': 'Updated company', 'customer_codes_to_add': [self.ccs.pk],
        })
        self.assertContains(response, 'CCS is already linked to OTHER.')
        self.commercial.refresh_from_db()
        self.assertEqual(self.commercial.name, 'Example company')
        self.assertTrue(other.sections.filter(source_customer=self.ccs).exists())

        response = self.client.post(self.change_url, {
            'code': 'ABC', 'name': 'Updated company', 'customer_links_to_remove': [section.pk],
        })
        self.assertContains(response, 'Select a valid choice.')
        self.assertTrue(other.sections.filter(pk=section.pk).exists())

    def test_unlink_code_without_deleting_customer(self):
        section = CustomerSection.objects.create(commercial_customer=self.commercial, source_customer=self.ccs)
        response = self.client.get(self.change_url)
        sidebar_urls = [
            model['admin_url']
            for app in response.context['available_apps']
            for model in app['models']
        ]
        self.assertIn(reverse('admin:clients_commercialcustomer_changelist'), sidebar_urls)
        self.assertNotIn(reverse('admin:clients_customersection_changelist'), sidebar_urls)
        self.assertContains(response, 'Tick the codes you want to unlink, then click Save.')
        self.assertContains(response, 'Unlink customer codes')
        self.assertContains(response, f'Unlink {self.ccs}')
        self.assertContains(response, 'id="id_customer_links_to_remove"')
        self.assertContains(response, f'name="customer_links_to_remove" value="{section.pk}"')

        section_url = reverse('admin:clients_customersection_change', args=[section.pk])
        response = self.client.get(section_url)
        self.assertContains(response, f'href="{self.change_url}#id_customer_links_to_remove"')
        self.assertContains(response, 'Unlink CCS in ABC')

        response = self.client.post(self.change_url, {
            'code': 'ABC', 'name': 'Example company', 'customer_links_to_remove': [section.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertQuerySetEqual(self.commercial.sections.values_list('source_customer__code', flat=True), ['ABC'])
        self.assertTrue(Customer.objects.filter(pk=self.ccs.pk).exists())
        response = self.client.get(self.search_url, {'term': 'CCS'})
        self.assertEqual(response.json()['results'], [{'id': str(self.ccs.pk), 'text': str(self.ccs)}])
        self.assertIn(str(self.ccs), LogEntry.objects.get(object_id=str(self.commercial.pk)).get_change_message())
