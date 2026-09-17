import unittest
from datetime import date
from core.finance.periods import period_bounds


class PeriodTests(unittest.TestCase):
    def test_all_and_leap_month(self):
        self.assertIsNone(period_bounds())
        self.assertEqual((date(2024,2,1),date(2024,2,29)),period_bounds(month='2024-02'))

    def test_year_and_date_limits(self):
        self.assertEqual((date(2024,1,1),date(2024,12,31)),period_bounds(year='2024'))
        self.assertEqual(date.max,period_bounds(year='9999')[1])
        self.assertEqual(date.max,period_bounds(month='9999-12')[1])

    def test_same_day_and_cross_year(self):
        self.assertEqual((date(2024,2,29),)*2,period_bounds(date_from='2024-02-29',date_to='2024-02-29'))
        self.assertEqual((date(2023,12,31),date(2024,1,1)),period_bounds(date_from='2023-12-31',date_to='2024-01-01'))

    def test_invalid_or_ambiguous(self):
        for params in [dict(year='2024',month='2024-01'),dict(year='0000'),dict(year='20240'),
                       dict(month='2024-13'),dict(month='2024-1'),dict(date_from='2024-01-01'),
                       dict(date_from='2024-03-01',date_to='2024-02-29'),
                       dict(date_from='2023-02-29',date_to='2023-03-01'),
                       dict(date_from='20240101',date_to='2024-01-02')]:
            with self.subTest(params=params),self.assertRaises(ValueError):period_bounds(**params)


if __name__=='__main__':unittest.main()
