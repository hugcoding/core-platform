"""Pure local tests: no database or bank files required."""
import unittest
from unittest.mock import patch
from core.finance.account_names import normalize_name,account_view


class AccountNameTests(unittest.TestCase):
    def test_normalize_and_reset(self):
        self.assertEqual('Spaarrekening',normalize_name('  Spaarrekening  '))
        self.assertEqual('Café',normalize_name('Cafe\u0301'))
        self.assertIsNone(normalize_name('   '))
        self.assertEqual('x'*80,normalize_name('x'*80))

    def test_reject_controls_and_invalid_input(self):
        for value in [None,123,{},'x'*81,'a\nb','a\tb','a\u202eb']:
            with self.assertRaises(ValueError):normalize_name(value)

    def test_account_response_contains_masked_identity_only(self):
        values={'original':{'iban':'NL91ABNA0417164300','label':'Rekening •4300'},
                'name':{'display_name':'Gezamenlijk'},'reset':{'display_name':None}}
        with patch('core.finance.account_names.decrypt',side_effect=values.__getitem__):
            row={'id':'synthetic','private_data':'original','name_data':'name','name_event_id':'event'}
            result=account_view(row)
            self.assertEqual('Gezamenlijk · •4300',result['label'])
            self.assertNotIn('iban',result)
            self.assertNotIn('NL91ABNA0417164300',str(result))
            for name_data in ('reset',None):
                self.assertEqual('Rekening •4300',account_view({**row,'name_data':name_data})['label'])


if __name__=='__main__':unittest.main()
