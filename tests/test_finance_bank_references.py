"""Only fabricated accounts and bank references."""
import unittest
from core.finance.camt import parse
from core.finance.bank_references import usable
from tests.test_finance import sample, IBAN


def account(n=1, bank='ASNB'):
    bban=bank+str(n).zfill(10)
    numeric=''.join(str(ord(c)-55) if c.isalpha() else c for c in bban+'NL00')
    return 'NL'+str(98-int(numeric)%97).zfill(2)+bban


def numbered(ref='SYNTHETIC-001', message='synthetic', n=1, bank='ASNB', **kwargs):
    data=sample(message=message,**kwargs).replace(IBAN.encode(),account(n,bank).encode())
    return data.replace(b'<Ntry>',('<Ntry><NtryRef>'+ref+'</NtryRef>').encode())


class ReferenceParserTests(unittest.TestCase):
    def test_entry_reference_is_not_message_or_payment_reference(self):
        entry=parse(numbered(ref='000001',message='another-download')).entries[0]
        self.assertEqual('000001',entry.entry_reference)
        self.assertTrue(usable(entry))
        self.assertEqual('NOTPROVIDED',entry.references[0]['EndToEndId'])
        for bank in ('ASNB','SNSB','RBRB'):
            self.assertTrue(usable(parse(numbered(bank=bank)).entries[0]))

    def test_other_banks_and_missing_numbers_do_not_gain_asn_guarantee(self):
        for ref,bank in [('', 'ASNB'),('NOTPROVIDED','ASNB'),('NONREF','ASNB'),('N/A','ASNB'),('123','ABNA')]:
            self.assertFalse(usable(parse(numbered(ref=ref,bank=bank)).entries[0]))


if __name__=='__main__':unittest.main()
