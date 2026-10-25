"""Shared evaluator and Finance adapter use fabricated dictionaries only."""
import copy
import unittest
from unittest.mock import patch
from core.recognition.rules import validate,matches
from core.finance.recognition_rules import plan


def rule(**changes):
    return dict(name='Synthetic interest',module='finance',active=True,
                when={'all':[{'field':'description','op':'contains','value':'rentebijschrijving'}]},
                set={'counterparty':'Synthetic Bank'},**changes)


class RecognitionRulesTests(unittest.TestCase):
    def test_module_scope_normalization_and_missing_fields(self):
        r=rule()
        self.assertTrue(matches(r,'finance',{'description':'RENTebijschrijving test'}))
        self.assertFalse(matches(r,'workset',{'description':'Rentebijschrijving'}))
        self.assertFalse(matches(r,'finance',{}))
        r['when']={'any':[{'field':'description','op':'contains','value':'salary'},{'field':'issuer','op':'equals','value':'asnbank'}]}
        self.assertTrue(matches(r,'finance',{'issuer':'ASNBANK'}))

    def test_same_engine_supports_workset_without_finance_fields(self):
        r=dict(name='Synthetic contract',module='workset',active=True,
               when={'all':[dict(field='filename',op='contains',value='contract')]},set={'category':'work_career'})
        self.assertTrue(matches(r,'workset',{'filename':'Employment CONTRACT.pdf'}))
        r['when']['all'][0]['field']='bank_code'
        with self.assertRaises(ValueError):validate(r)

    def test_no_arbitrary_code_unknown_fields_or_unbounded_rules(self):
        for change in [dict(script='print(1)'),dict(set={'execute':'delete'}),dict(when={'all':[]}),dict(name='x\nsecret'),dict(active='true')]:
            r=rule();r.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):validate(r)
        r=rule();r['when']['all'][0]['op']='regex'
        with self.assertRaises(ValueError):validate(r)

    def test_explicit_exclusion_does_not_broaden_conditions(self):
        r=rule();r['exclude']=['excluded']
        self.assertFalse(matches(r,'finance',{'_id':'excluded','description':'Rentebijschrijving'}))
        self.assertTrue(matches(r,'finance',{'_id':'included','description':'Rentebijschrijving'}))

    def test_missing_party_can_be_confirmed_without_changing_manual_category(self):
        row=dict(id='t',account_id='a',amount='0.02',currency='EUR',confirmed=True,transaction_type='INCOME',
                 category_code='inkomen',subcategory_code='inkomen_rente',merchant_id=None,merchant_data=None)
        decision=plan(row,{'description':'Rentebijschrijving'},rule(),[])
        self.assertEqual('eligible',decision['status'])
        self.assertEqual({'counterparty':'Synthetic Bank'},decision['changes'])
        self.assertEqual('inkomen_rente',decision['desired']['subcategory_code'])
        with patch('core.finance.recognition_rules.decrypt',return_value={'name':'My confirmed bank'}):
            decision=plan({**row,'merchant_id':'owner','merchant_data':'encrypted'}, {'description':'Rentebijschrijving'},rule(),[])
        self.assertEqual('protected',decision['status'])

    def test_bad_category_and_bank_namespace_pairs_abstain(self):
        row=dict(id='t',account_id='a',amount='1',currency='EUR',transaction_type='INCOME')
        r=rule();r['set']={'category':'missing'}
        self.assertEqual('invalid_category',plan(row,{'description':'rentebijschrijving'},r,[])['status'])
        r=rule();r['when']={'all':[dict(field='issuer',op='equals',value='ASNBANK'),dict(field='bank_code',op='equals',value='6607')]}
        payload=dict(bank_codes=[{'issuer':'ASNBANK','proprietary':'1234'},{'issuer':'OTHER','proprietary':'6607'}])
        self.assertIsNone(plan(row,payload,r,[]))
        for extra in [dict(reversal='true'),dict(details=[{},{}])]:
            self.assertIsNone(plan(row,{**extra,'description':'rentebijschrijving'},rule(),[]))

    def test_aligned_and_case_normalized_names_do_not_repeat(self):
        row=dict(id='t',account_id='a',amount='1',currency='EUR',transaction_type='INCOME',merchant_id='m',merchant_data='encrypted')
        with patch('core.finance.recognition_rules.decrypt',return_value={'name':'SYNTHETIC BANK'}):
            self.assertEqual('aligned',plan(row,{'description':'Rentebijschrijving'},rule(),[])['status'])

    def test_confirmation_does_not_freeze_an_unknown_category(self):
        row=dict(id='t',account_id='a',amount='1',currency='EUR',transaction_type='INCOME',confirmed=False,merchant_id=None,merchant_data=None)
        payload={'description':'Rentebijschrijving'}
        self.assertEqual('eligible',plan(row,payload,rule(),[])['status'])
        self.assertEqual('needs_category',plan(row,payload,rule(),[],owner_confirmation=True)['status'])
        self.assertEqual('protected',plan({**row,'transaction_type':'TRANSFER'},payload,rule(),[])['status'])


class AlignedConfirmationTests(unittest.TestCase):
    def test_correct_automatic_classification_can_be_confirmed_without_value_change(self):
        row=dict(id='t',account_id='a',amount='1',currency='EUR',transaction_type='INCOME',category_code='inkomen',subcategory_code='inkomen_rente',confirmed=False,merchant_id='m',merchant_data='encrypted')
        with patch('core.finance.recognition_rules.decrypt',return_value={'name':'Synthetic Bank'}):
            auto=plan(row,{'description':'Rentebijschrijving'},rule(),[])
            owner=plan(row,{'description':'Rentebijschrijving'},rule(),[],owner_confirmation=True)
            confirmed=plan({**row,'confirmed':True},{'description':'Rentebijschrijving'},rule(),[],owner_confirmation=True)
        self.assertEqual('aligned',auto['status'])
        self.assertEqual(('eligible',{},True),(owner['status'],owner['changes'],owner['confirmation_only']))
        self.assertEqual('aligned',confirmed['status'])


if __name__=='__main__':unittest.main()
