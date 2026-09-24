"""Synthetic bank evidence; no private files or external services."""
import unittest
from core.finance.balances import summarize
from core.finance.camt import parse, ImportErrorCode
from tests.test_finance import sample


def with_balances(data=None, opening='20.00', closing='7.66', opening_date='2026-08-31', closing_date='2026-09-01'):
    def bal(kind, value, day):
        date = f'<Dt><Dt>{day}</Dt></Dt>' if day else ''
        direction = 'DBIT' if value.startswith('-') else 'CRDT'
        return f'<Bal><Tp><CdOrPrtry><Cd>{kind}</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">{value.lstrip("-")}</Amt><CdtDbtInd>{direction}</CdtDbtInd>{date}</Bal>'
    return (data or sample()).replace(b'</Acct>', ('</Acct>'+bal('OPBD', opening, opening_date)+bal('CLBD', closing, closing_date)).encode())


class BalanceTests(unittest.TestCase):
    def test_preserves_signed_balances_dates_and_statement_location(self):
        p = parse(with_balances(opening='0.00', closing='-12.34'))
        self.assertEqual('0.00', p.bank_balances[0]['opening'])
        self.assertEqual('-12.34', p.bank_balances[0]['closing'])
        self.assertEqual('2026-09-01', p.bank_balances[0]['closing_date'])
        self.assertEqual('stmt:1', p.bank_balances[0]['locator'])
        no_entries = parse(with_balances(sample(count=0), closing='20.00'))
        self.assertEqual(0, len(no_entries.entries))
        self.assertEqual(1, len(no_entries.bank_balances))
        missing = parse(with_balances(closing_date=''))
        self.assertIsNone(missing.bank_balances[0]['closing_date'])
        with self.assertRaisesRegex(ImportErrorCode, 'invalid_date'):
            parse(with_balances(closing_date='2026-02-30'))

    def test_no_extrapolation_or_false_total_for_gaps_conflicts_or_missing_accounts(self):
        accounts=[{'id':'a','label':'Synthetic A'},{'id':'b','label':'Synthetic B'}]
        snap=dict(account_id='a',opening='100.00',closing='80.00',opening_date='2026-08-31',
                  closing_date='2026-09-01',source_id='source',locator='stmt:1')
        second={**snap,'account_id':'b','closing':'-10.00'}
        result=summarize(accounts,[snap,second],end='2026-09-30')
        self.assertEqual('70.00',result['total'])
        self.assertEqual('2026-09-01',result['as_of']) # Never projected to Sep 30.
        for evidence in ([snap], [snap,{**second,'closing_date':'2026-09-02'}],
                         [snap,second,{**snap,'closing':'81.00'}]):
            self.assertIsNone(summarize(accounts,evidence)['total'])
        self.assertIsNone(summarize(accounts,[snap,second],pending=1)['total'])
        self.assertIsNone(summarize(accounts,[snap,second],end='2026-08-30')['total'])
        self.assertIsNone(summarize(accounts,[{**snap,'closing_date':None}])['total'])
        self.assertIsNone(summarize([],[])['total'])
        self.assertEqual('70.00',summarize(accounts,[snap,second,snap])['total']) # Repeated bank evidence.


if __name__=='__main__': unittest.main()
