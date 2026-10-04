"""Recurrence tests use fabricated observations only."""
from datetime import date, timedelta
from decimal import Decimal
import unittest

from core.finance.recurring import detect


def series(dates, amounts=None):
    return [{'id': str(i), 'booking_date': date.fromisoformat(d),
             'amount': Decimal(str((amounts or [-12]*len(dates))[i]))} for i, d in enumerate(dates)]


class DetectionTests(unittest.TestCase):
    def test_monthly_without_any_classification(self):
        result = detect(series(['2026-06-18','2026-07-18','2026-08-18','2026-09-18']))
        self.assertEqual('monthly', result['cadence'])
        self.assertEqual('2026-10-18', result['next_expected'])
        self.assertEqual(4, result['observation_count'])
        self.assertEqual('-12.00', result['typical_amount'])
        self.assertGreaterEqual(result['confidence'], .8)

    def test_date_drift_and_variable_amounts(self):
        result = detect(series(['2026-06-18','2026-07-18','2026-08-19','2026-09-18'], [-117,-124,-119,-131]))
        self.assertEqual('monthly', result['cadence'])
        self.assertEqual('-121.50', result['typical_amount'])
        self.assertEqual('2026-10-18', result['next_expected'])
        self.assertGreater(Decimal(result['amount_variation']), 0)

    def test_all_cadences(self):
        for cadence, dates, expected in [
            ('quarterly', ['2026-01-18','2026-04-18','2026-07-19'], '2026-10-18'),
            ('yearly', ['2024-09-18','2025-09-19','2026-09-18'], '2027-09-18'),
        ]:
            with self.subTest(cadence=cadence):
                result = detect(series(dates))
                self.assertEqual(cadence, result['cadence'])
                self.assertEqual(expected, result['next_expected'])

    def test_missed_period_and_amount_outlier_survive(self):
        result = detect(series(['2026-05-18','2026-06-18','2026-08-18','2026-09-18'], [-12,-12,-120,-12]))
        self.assertEqual('monthly', result['cadence'])
        self.assertEqual(1, result['missed_periods'])
        self.assertEqual('-12.00', result['typical_amount'])
        self.assertEqual('-120', result['amount_min'])

    def test_one_timing_outlier_in_long_series(self):
        result = detect(series(['2026-04-18','2026-05-18','2026-06-26','2026-07-18','2026-08-18']))
        self.assertEqual('monthly', result['cadence'])
        self.assertEqual(1, result['timing_outliers'])

    def test_month_end_and_leap_year(self):
        result = detect(series(['2026-01-31','2026-02-28','2026-03-31']))
        self.assertEqual('2026-04-30', result['next_expected'])
        self.assertTrue(result['month_end'])
        result = detect(series(['2024-02-29','2025-02-28','2026-02-28']))
        self.assertEqual('yearly', result['cadence'])
        self.assertEqual('2027-02-28', result['next_expected'])

    def test_insufficient_incidental_and_irregular_abstain(self):
        for dates in [[], ['2026-01-18'], ['2026-01-18','2026-02-18'],
                      ['2026-01-02','2026-01-11','2026-04-27','2026-07-04'],
                      ['2026-01-01','2026-02-15','2026-03-28','2026-04-06'],
                      ['2026-01-18','2026-02-18','2026-02-18','2026-03-18']]:
            self.assertIsNone(detect(series(dates)))

    def test_order_independent_and_mixed_direction_abstains(self):
        rows = series(['2026-01-18','2026-02-18','2026-03-18'])
        self.assertEqual(detect(rows), detect(list(reversed(rows))))
        rows[-1]['amount'] = Decimal(12)
        self.assertIsNone(detect(rows))

    def test_large_weekly_series_not_recurring(self):
        rows = [{'id': str(i), 'booking_date': date(2000,1,3)+timedelta(days=i*7),
                 'amount': Decimal(-12)} for i in range(10000)]
        self.assertIsNone(detect(rows))

    def test_price_increase_does_not_break_calendar_pattern(self):
        result=detect(series(['2026-01-28','2026-02-28','2026-03-28','2026-04-28'],[-17.99,-17.99,-21.99,-21.99]))
        self.assertEqual('monthly',result['cadence'])
        self.assertEqual('22.23',result['price_change_percent'])
        self.assertEqual('17.99',result['previous_amount'])
        self.assertEqual('2026-01-28',result['first_observed'])
        self.assertIsNone(detect(series(['2026-01-01','2026-01-02','2026-01-03'])))
        self.assertIsNone(detect(series(['2026-01-01','2026-01-08','2026-01-15'])))

    def test_classification_evidence_advises_without_confirming(self):
        from core.finance.recurring import type_proposal
        item={**detect(series(['2026-01-28','2026-02-28','2026-03-28'])),
              'active':True,'direction':'debit','status':'proposed','recurring_type':'other_recurring',
              'classifications':[{'category_code':'abonnementen','subcategory_code':'abonnementen_telefoon','transaction_type':'EXPENSE','confirmed_count':2}]}
        self.assertEqual('subscription',type_proposal(item));self.assertEqual('proposed',item['status'])
        for changes in ({'cadence':'weekly'},{'observation_count':2},{'missed_periods':4},{'amount_variation':'2'},
                        {'reviewed_type':'fixed_cost'},{'direction':'credit'},{'components':[{},{}]},
                        {'classifications':[{'category_code':'boodschappen','transaction_type':'EXPENSE','confirmed_count':3}]},
                        {'classifications':[{'category_code':'abonnementen','transaction_type':'TRANSFER','confirmed_count':3}]},
                        {'classifications':[{'category_code':'abonnementen','transaction_type':'EXPENSE','confirmed_count':0}]}):
            self.assertEqual('other_recurring',type_proposal({**item,**changes}))
        item['classifications'][0]['subcategory_code']='abonnementen_streaming'
        self.assertEqual('subscription',type_proposal(item))

    def test_preview_spreads_over_time_and_includes_extremes(self):
        from core.finance.recurring import preview_ids
        rows=[{'id':str(i),'booking_date':date(2020,1,1)+timedelta(days=i)} for i in range(80)]
        rows += [{'id':str(80+i),'booking_date':date(2026,1,1)+timedelta(days=i*10)} for i in range(40)]
        ids=preview_ids(rows)
        self.assertEqual(50,len(ids));self.assertEqual(50,len(set(ids)))
        self.assertEqual('0',ids[0]);self.assertEqual('119',ids[-1])
        self.assertGreater(sum(int(i)>=80 for i in ids),5)
        self.assertEqual(ids,preview_ids(rows))
        self.assertEqual(['0','1'],preview_ids(rows[:2]))
        self.assertEqual([],preview_ids([]))


if __name__ == '__main__':
    unittest.main()
