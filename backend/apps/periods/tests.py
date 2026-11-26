from django.test import TestCase
from datetime import date
from rest_framework.test import APIClient
from apps.accounts.models import Firm, User
from apps.periods.models import FinancialYear, Period
from apps.periods.generator import generate_financial_years_for_firm

class PeriodsAndGeneratorTests(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='Periods CA Firm', fy_start_month=4)
        self.admin = User.objects.create_user(email='admin@periods.com', firm=self.firm, system_role=User.Role.ADMIN)

    def test_assessment_year_derivation(self):
        fy = FinancialYear.objects.create(
            firm=self.firm,
            label='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31)
        )
        self.assertEqual(fy.assessment_year_label, '2026-27')

    def test_period_generation_structure_and_counts(self):
        # Generate 1 year: 2024-25 (includes leap year Feb 2025 is 28 days, Feb 2024 is 29 days)
        generate_financial_years_for_firm(self.firm, start_calendar_year=2024, end_calendar_year=2024)

        fy = FinancialYear.objects.get(firm=self.firm, label='2024-25')
        self.assertEqual(fy.start_date, date(2024, 4, 1))
        self.assertEqual(fy.end_date, date(2025, 3, 31))

        # 12 Months
        months = fy.periods.filter(kind=Period.Kind.MONTH).order_by('sequence')
        self.assertEqual(months.count(), 12)
        # Sequence 1: Apr 2024
        self.assertEqual(months[0].label, 'Apr 2024')
        self.assertEqual(months[0].start_date, date(2024, 4, 1))
        self.assertEqual(months[0].end_date, date(2024, 4, 30))

        # Sequence 11: Feb 2025
        self.assertEqual(months[10].label, 'Feb 2025')
        self.assertEqual(months[10].end_date, date(2025, 2, 28))

        # Sequence 12: Mar 2025
        self.assertEqual(months[11].label, 'Mar 2025')
        self.assertEqual(months[11].end_date, date(2025, 3, 31))

        # 4 Quarters
        quarters = fy.periods.filter(kind=Period.Kind.QUARTER).order_by('sequence')
        self.assertEqual(quarters.count(), 4)
        self.assertEqual(quarters[0].label, 'Q1 2024-25')
        self.assertEqual(quarters[0].start_date, date(2024, 4, 1))
        self.assertEqual(quarters[0].end_date, date(2024, 6, 30))

        # 2 Half-Years
        halves = fy.periods.filter(kind=Period.Kind.HALF).order_by('sequence')
        self.assertEqual(halves.count(), 2)
        self.assertEqual(halves[0].label, 'H1 2024-25')
        self.assertEqual(halves[0].start_date, date(2024, 4, 1))
        self.assertEqual(halves[0].end_date, date(2024, 9, 30))

        # 1 Full Year
        year_period = fy.periods.filter(kind=Period.Kind.YEAR).first()
        self.assertIsNotNone(year_period)
        self.assertEqual(year_period.label, 'FY 2024-25')

    def test_periods_api_endpoints_and_filtering(self):
        generate_financial_years_for_firm(self.firm, start_calendar_year=2026, end_calendar_year=2026)
        client = APIClient()
        client.force_authenticate(user=self.admin)

        # FY list
        res_fy = client.get('/api/v1/periods/financial-years/')
        self.assertEqual(res_fy.status_code, 200)
        self.assertTrue(len(res_fy.data['results']) >= 1)

        # Filter periods by kind=month
        res_m = client.get('/api/v1/periods/periods/?kind=month')
        self.assertEqual(res_m.status_code, 200)
        self.assertTrue(len(res_m.data['results']) >= 12)
