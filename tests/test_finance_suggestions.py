import unittest
from core.finance.suggestions import identity, recognized_merchant


class SuggestionIdentityTests(unittest.TestCase):
    def test_ovpay_ignores_variable_dates_references_and_amounts(self):
        first={'description':'www.ovpay01.01.2020 TEST111 MCC:4111 Apple Pay'}
        second={'description':'WWW.OVPAY31.12.2022 TEST999 MCC:4111 Apple Pay'}
        self.assertEqual(identity(first,'-1.20','EUR'),identity(second,'-8.95','EUR'))

    def test_generic_card_text_does_not_match(self):
        for text in ('MCC:4111 Apple Pay NEDERLAND','notovpay','ovpayment','OVPAYMENT'):
            self.assertIsNone(identity({'description':text},'-1','EUR'))

    def test_direction_currency_and_zero(self):
        payload={'description':'OVpay'}
        self.assertNotEqual(identity(payload,-1,'EUR'),identity(payload,1,'EUR'))
        self.assertNotEqual(identity(payload,-1,'EUR'),identity(payload,-1,'USD'))
        self.assertIsNone(identity(payload,0,'EUR'))

    def test_named_counterparty_requires_same_account(self):
        a={'counterparty':'Demo Energie','counteraccount':'TEST 123'}
        b={'counterparty':'DEMO   ENERGIE','counteraccount':'test123'}
        self.assertEqual(identity(a,-1,'EUR'),identity(b,-2,'EUR'))
        self.assertNotEqual(identity(a,-1,'EUR'),identity({**b,'counteraccount':'TEST456'},-1,'EUR'))
        self.assertIsNone(identity({'counterparty':'Demo Energie'},-1,'EUR'))

    def test_mixed_batch_is_not_a_single_merchant(self):
        self.assertIsNone(identity({'description':'OVpay','details':[{},{}]},-5,'EUR'))

    def test_known_merchant_markers_are_specific_and_ignore_terminal_numbers(self):
        for first,second,name in [('SHELL STATION 1234 TEST','Shell station 9876 TEST','Shell'),
                                  ('AH 1234 TEST','Albert Heijn 9876 TEST','Albert Heijn')]:
            self.assertEqual(name,recognized_merchant({'description':first}))
            self.assertEqual(identity({'description':first},-1,'EUR'),identity({'description':second},-9,'EUR'))
        for description in ('shellfish restaurant','ah wonderful day','Invoice mentioning SHELL STATION 1234','AH 12'):
            self.assertIsNone(recognized_merchant({'description':description}))
        self.assertIsNone(recognized_merchant({'description':'SHELL STATION 1234','details':[{},{}]}))

    def test_processors_and_unknown_parties_are_not_identity(self):
        for name in ('Mollie','Adyen Payments','Onbekende tegenpartij','Apple Pay'):
            self.assertIsNone(identity({'counterparty':name,'counteraccount':'TEST123'},-1,'EUR'))


if __name__=='__main__': unittest.main()
