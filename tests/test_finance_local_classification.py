import json
import os
import unittest
from unittest.mock import patch, Mock

from core.finance import local_classification as local
from core.finance.suggestions import identity


class LocalClassificationTests(unittest.TestCase):
    categories = [dict(id='a', code='vervoer', parent_id=None, transaction_type='EXPENSE', name='Vervoer'),
                  dict(id='b', code='vervoer_ov', parent_id='a', transaction_type='EXPENSE', name='OV')]

    def target(self, description='Synthetische metro betaling'):
        return dict(id='target', account_id='account', amount=-10, currency='EUR',
                    private_data=dict(description=description, counterparty='Synthetic transport'))

    def call(self, answer, target=None, examples=None, categories=None):
        infer = Mock(return_value=answer)
        with patch.object(local, 'decrypt', side_effect=lambda v: v):
            result = local.decide(target or self.target(), examples or [], categories or self.categories, ({}, {}), infer)
        return result, infer

    def test_valid_category_is_automatic_and_prompt_contains_no_amount(self):
        result, infer = self.call(dict(category='vervoer', subcategory='vervoer_ov', confidence=.9))
        self.assertEqual('AI', result['source'])
        self.assertEqual('EXPENSE', result['transaction_type'])
        data = json.loads(infer.call_args.args[0].user_prompt)
        self.assertNotIn('amount', data['payment'])
        self.assertEqual('debit', data['payment']['direction'])

    def test_uncertain_invalid_and_cross_parent_answers_abstain(self):
        for answer in ({}, {'category':'invented','confidence':1}, {'category':'vervoer','confidence':True},
                       {'category':'vervoer','confidence':.4}, {'category':'vervoer','confidence':float('nan')},
                       {'category':'vervoer','subcategory':'invented','confidence':.99}):
            self.assertIsNone(self.call(answer)[0])

    def test_transfer_requires_deterministic_group_evidence(self):
        categories=[{**self.categories[0], 'transaction_type':'TRANSFER'}]
        self.assertIsNone(self.call({'category':'vervoer','confidence':1}, categories=categories)[0])

    def test_existing_matcher_uses_owner_example_without_llm(self):
        target = self.target('www.ovpay01.09.2026')
        payload = target['private_data']
        example = dict(identity=identity(payload,-10,'EUR'), review_id='owner-review', transaction_type='EXPENSE',
                       category_code='vervoer', subcategory_code='vervoer_ov', merchant_id=None)
        result, infer = self.call({}, target=target, examples=[example])
        infer.assert_not_called()
        self.assertEqual('MERCHANT',result['source'])
        self.assertEqual('owner-review',result['seed'])
        self.assertIsNone(self.call({}, target=target, examples=[example,{**example,'category_code':'other'}])[0])

    def test_local_context_removes_account_numbers_digits_and_email(self):
        result = local.context_text({'description':'NL91 ABNA 0417 1643 00 test@example.com card 1234567890123456',
                                     'counterparty':'Synthetic shop'},-4)
        self.assertNotIn('ABNA',result['description'])
        self.assertNotIn('@',result['description'])
        self.assertFalse(any(c.isdigit() for c in result['description']))

    def test_ah_card_payment_reuses_manual_category_without_llm(self):
        target = self.target('NLTEST000002>AH BOUWENS>TESTSTAD')
        example = dict(identity=identity({'description':'NLTEST000001>ALBERT HEIJN BOUWENS>TESTSTAD'},-15,'EUR'),
                       review_id='synthetic-owner-review',transaction_type='EXPENSE',category_code='boodschappen',
                       subcategory_code='supermarkt',merchant_id=None)
        categories=[dict(id='shop',code='boodschappen',parent_id=None,transaction_type='EXPENSE',name='Boodschappen'),
                    dict(id='super',code='supermarkt',parent_id='shop',transaction_type='EXPENSE',name='Supermarkt')]
        result,infer=self.call({},target=target,examples=[example],categories=categories)
        infer.assert_not_called()
        self.assertEqual(('MERCHANT','boodschappen','supermarkt'),
                         (result['source'],result['category_code'],result['subcategory_code']))

    def test_only_literal_local_addresses_no_proxy_or_redirect(self):
        for endpoint in ('https://api.example.com/v1','http://8.8.8.8/v1','http://169.254.169.254',
                         'http://192.168.1.2@8.8.8.8','http://localhost/v1','http://192.168.1.2/v1?secret=x'):
            with patch.dict(os.environ, CORE_LLM_ENDPOINT=endpoint), self.assertRaises(ValueError):
                local.settings()
        with patch.dict(os.environ, CORE_LLM_ENDPOINT='http://192.168.1.2:11434/v1'):
            self.assertEqual('http://192.168.1.2:11434/v1',local.settings()[0])
        with self.assertRaises(ValueError):
            local.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_http_error_does_not_echo_payload(self):
        opener=Mock();opener.open.side_effect=RuntimeError('synthetic private content')
        with patch.object(local,'build_opener',return_value=opener), self.assertRaisesRegex(RuntimeError,'^finance_local_llm_unavailable$'):
            local.generate(local.GenerationRequest('synthetic','system','private'))

    def test_group_context_shares_known_shop_but_keeps_generic_purpose(self):
        a=local.inference_context({'description':'NLTEST000001>AH BOUWENS>TESTSTAD 01.01.2026'},-12,'EUR')
        b=local.inference_context({'description':'NLTEST000002>ALBERT HEIJN BOUWENS>TESTSTAD 02.02.2026'},-45,'EUR')
        self.assertEqual(a,b)
        self.assertNotEqual(a,local.inference_context({'description':'NLTEST000003>ALBERT HEIJN BOUWENS>TESTSTAD'},12,'EUR'))
        recipient={'counterparty':'Synthetic person','counteraccount':'synthetic'}
        self.assertNotEqual(local.inference_context({**recipient,'description':'Rent'},-5,'EUR'),
                            local.inference_context({**recipient,'description':'Birthday gift'},-5,'EUR'))

    def test_batch_bounds_and_single_new_inference(self):
        infer=Mock(return_value={})
        request=local.GenerationRequest('synthetic','system','synthetic')
        def one(conn,job,cache,call):
            call(request)
            return True
        with patch.object(local,'_step',side_effect=one) as single:
            self.assertTrue(local.step(None,'job',{'phase':'llm'},infer))
        self.assertEqual(2,single.call_count)
        self.assertEqual(1,infer.call_count)
        with patch.object(local,'_step',return_value=True) as single:
            self.assertTrue(local.step(None,'job',{'phase':'llm'},infer))
        self.assertEqual(local.BATCH_SIZE,single.call_count)

    def test_batch_finishes_and_failure_is_not_swallowed(self):
        with patch.object(local,'_step',side_effect=[True,True,False]):
            self.assertTrue(local.step(None,'job',{}))
        with patch.object(local,'_step',return_value=False):
            self.assertFalse(local.step(None,'job',{}))
        with patch.object(local,'_step',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):local.step(None,'job',{})

    def test_new_inference_never_waits_while_previous_results_hold_job_lock(self):
        infer=Mock(return_value={})
        n=0
        def one(conn,job,cache,call):
            nonlocal n
            n+=1
            if n>1:call(local.GenerationRequest('synthetic','system','synthetic'))
            return True
        with patch.object(local,'_step',side_effect=one):
            self.assertTrue(local.step(None,'job',{'phase':'llm'},infer))
        infer.assert_not_called()

    def test_core_pass_defers_without_model_configuration_or_request(self):
        infer=Mock()
        with patch.object(local,'decrypt',side_effect=lambda v:v), patch.object(local,'settings',side_effect=AssertionError('No model needed')):
            with self.assertRaises(local.NeedsLLM):
                local.decide(self.target(),[],self.categories,({},{}),infer,allow_llm=False)
        infer.assert_not_called()

    def test_bank_type_prevents_incompatible_llm_category(self):
        target={**self.target(), 'transaction_type':'EXPENSE','classification_source':'RULE'}
        categories=[dict(id='income',code='income',parent_id=None,transaction_type='INCOME',name='Income')]
        result,_=self.call(dict(category='income',confidence=.95),target=target,categories=categories)
        self.assertIsNone(result)
        result,_=self.call(dict(category='vervoer',confidence=.95),target=target)
        self.assertEqual('EXPENSE',result['transaction_type'])
