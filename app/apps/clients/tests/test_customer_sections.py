from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

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
