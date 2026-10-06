"""Fabricated XML only; no private bank files are read."""
from dataclasses import replace
import unittest
from core.finance.camt import parse
from core.finance.bank_types import recognize
from tests.test_finance_bank_references import numbered


def coded(number='', domain='', family='', subfamily='', credit=False, reversal='', bank='ASNB'):
    code=f'<BkTxCd><Domn><Cd>{domain}</Cd><Fmly><Cd>{family}</Cd><SubFmlyCd>{subfamily}</SubFmlyCd></Fmly></Domn><Prtry><Cd>{number}</Cd><Issr>Bank</Issr></Prtry></BkTxCd>'
    data=numbered(bank=bank).replace(b'<Sts>',(code+f'<RvslInd>{reversal}</RvslInd><Sts>').encode())
    return data.replace(b'DBIT',b'CRDT') if credit else data


class BankTypeTests(unittest.TestCase):
    def test_documented_asn_codes(self):
        for number,credit,kind in [('7903',False,'EXPENSE'),('9928',False,'EXPENSE'),
                ('6903',True,'CORRECTION'),('9714',False,'EXPENSE'),('8715',True,'CORRECTION'),
                ('6607',True,'INCOME'),('6606',True,'CORRECTION'),('7606',False,'EXPENSE'),
                ('7617',False,'EXPENSE'),('6617',True,'CORRECTION')]:
            with self.subTest(number=number):
                self.assertEqual(kind,recognize(parse(coded(number,credit=credit)).entries[0])[0])

    def test_bank_independent_card_code_and_reversal(self):
        for credit,kind in [(False,'EXPENSE'),(True,'CORRECTION')]:
            entry=parse(coded(domain='PMNT',family='CCRD',subfamily='POSD',credit=credit,bank='ABNA')).entries[0]
            self.assertEqual(kind,recognize(entry)[0])
        self.assertEqual('CORRECTION',recognize(parse(coded(reversal='YES')).entries[0])[0])
        self.assertEqual('-12.34',parse(coded(reversal='YES')).entries[0].amount)

    def test_cash_transfers_missing_codes_and_other_bank_numbers_abstain(self):
        for data in [numbered(),coded('7903',bank='ABNA'),coded('7903',credit=True),
                     coded(domain='PMNT',family='CCRD',subfamily='CWDL'),
                     coded(domain='PMNT',family='ICDT',subfamily='ESCT'),coded(credit=True)]:
            self.assertEqual('UNKNOWN',recognize(parse(data).entries[0])[0])

    def test_aggregate_conflicting_detail_and_unknown_reversal_abstain(self):
        entry=parse(coded('7903')).entries[0]
        self.assertEqual('UNKNOWN',recognize(replace(entry,details=({},{})))[0])
        self.assertEqual('UNKNOWN',recognize(replace(entry,reversal='not-a-boolean'))[0])
        self.assertEqual('UNKNOWN',recognize(replace(entry,bank_codes=entry.bank_codes+({'proprietary':'7225'},)))[0])

    def test_metadata_does_not_change_transaction_identity(self):
        from core.finance.store import entry_fingerprint
        from unittest.mock import patch
        entry=parse(numbered()).entries[0]
        enriched=replace(entry,bank_codes=({'proprietary':'7903'},),reversal='YES')
        with patch('core.finance.store.fingerprint',side_effect=lambda domain,values:values):
            self.assertEqual(entry_fingerprint(entry,'account'),entry_fingerprint(enriched,'account'))


if __name__=='__main__': unittest.main()
