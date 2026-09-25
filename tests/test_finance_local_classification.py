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
