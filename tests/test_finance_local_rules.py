import unittest
from unittest.mock import Mock,patch
from core.finance.local_rules import decide,RULES
from core.finance import local_classification as local


class LocalRuleTests(unittest.TestCase):
    categories=[dict(code=code,id=code,parent_id=None,transaction_type='EXPENSE')
                for code in sorted({r[1] for r in RULES}|{'financieel'})]+[
                    dict(code='inkomen',id='income',parent_id=None,transaction_type='INCOME')]
    def classify(self,party='',description='',amount=-20,**evidence):
        payload=dict(counterparty=party,description=description)
        return decide(dict(amount=amount,**evidence),payload,self.categories)

    def test_broad_categories_without_owner_example(self):
        for party,code in [('Albert Heijn Bouwens','boodschappen'),('Jumbo filiaal 42','boodschappen'),
                ('Fietsaccuwinkel B.V.','vervoer'),('Rijwielhandel Voorbeeld','vervoer'),
                ('Spotify AB by Adyen','abonnementen'),('Restaurant Voorbeeld','eten_drinken'),
                ('Vattenfall','wonen'),('VGZ','verzekeringen'),('Zeeman','kleding')]:
            with self.subTest(party=party):
                choice=self.classify(party)
                self.assertEqual((code,'RULE',None),(choice['category_code'],choice['source'],choice['subcategory_code']))

    def test_domain_and_card_fields_but_not_private_memos(self):
        self.assertEqual('vervoer',self.classify('Mollie', '12345 fietsaccuwinkel.nl')['category_code'])
        self.assertEqual('boodschappen',self.classify('', 'LIDL FILIAAL>TESTSTAD 01.01.2026')['category_code'])
        for party,text in [('Jan Jansen','fietsaccuwinkel.nl'),('Jan Bakker','fiets gekocht'),
                ('','betaling fiets supermarkt restaurant'),('Adyen','123456'),('','jan@example.nl')]:
            self.assertIsNone(self.classify(party,text))

    def test_uncertain_credit_conflict_and_aggregate_stay_open(self):
        self.assertIsNone(self.classify('Albert Heijn',amount=20))
        self.assertIsNone(self.classify('Albert Heijn','fietsaccuwinkel.nl'))
        self.assertIsNone(decide({'amount':-20},{'counterparty':'Lidl','details':[{},{}]},self.categories))
        self.assertIsNone(self.classify('Lidl',transaction_type='TRANSFER',classification_source='RULE'))
        choice=self.classify('Lidl',amount=20,transaction_type='CORRECTION',classification_source='RULE')
        self.assertEqual('CORRECTION',choice['transaction_type'])

    def test_structured_bank_evidence_and_benefit(self):
        self.assertEqual('inkomen',self.classify(amount=2,classification_source='RULE',transaction_type='INCOME',rule_version='bank-type-v1:interest_received')['category_code'])
        self.assertEqual('financieel',self.classify(classification_source='RULE',transaction_type='EXPENSE',rule_version='bank-type-v1:bank_fee')['category_code'])
        self.assertEqual('inkomen',self.classify('UWV',amount=20)['category_code'])

    def test_inactive_or_retyped_categories_are_not_created_or_used(self):
        for categories in ([],[dict(code='vervoer',parent_id=None,transaction_type='TRANSFER')],
                           [dict(code='vervoer',parent_id=None,transaction_type='EXPENSE',active=False)]):
            self.assertIsNone(decide({'amount':-20},{'counterparty':'Fietswinkel'},categories))

    def test_core_rule_needs_neither_model_nor_inference(self):
        infer=Mock(side_effect=AssertionError('No AI'))
        target=dict(amount=-20,currency='EUR',private_data={'counterparty':'Fietsaccuwinkel B.V.'})
        with patch.object(local,'decrypt',side_effect=lambda v:v),patch.object(local,'settings',side_effect=AssertionError('No model')):
            result=local.decide(target,[],self.categories,({},{}),infer,allow_llm=False)
        self.assertEqual('RULE',result['source']);infer.assert_not_called()

    def test_manual_correction_overrides_coarse_rule_on_next_payment(self):
        from core.finance.suggestions import identity
        payload={'counterparty':'Fietsaccuwinkel B.V.'}
        example=dict(identity=identity(payload,-20,'EUR'),review_id='owner',category_code='vrije_tijd',
                     subcategory_code=None,transaction_type='EXPENSE',merchant_id=None)
        self.assertIsNotNone(example['identity'])
        categories=self.categories+[dict(code='vrije_tijd',id='hobby',parent_id=None,transaction_type='EXPENSE')]
        target=dict(amount=-30,currency='EUR',private_data={'counterparty':'Fietsaccuwinkel BV'})
        with patch.object(local,'decrypt',side_effect=lambda v:v):
            result=local.decide(target,[example],categories,({},{}),allow_llm=False)
        self.assertEqual(('MERCHANT','vrije_tijd','owner'),(result['source'],result['category_code'],result['seed']))


if __name__=='__main__':unittest.main()
