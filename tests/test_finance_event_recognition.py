"""Fabricated CAMT only. Never reads exports, production secrets or transactions."""
from dataclasses import asdict
import unittest
from unittest.mock import Mock,patch
from core.finance.camt import parse
from core.finance import event_recognition as events,local_classification as local
from tests.test_finance_bank_references import numbered


def rent_xml(marker='synthetic-event',date='2026-09-05'):
    import re
    data=numbered(message=marker,ref=marker,n=818181,description='SYNTHETIC INTEREST')
    data=re.sub(b'<NtryDtls>.*?</NtryDtls>',b'<NtryDtls><TxDtls/></NtryDtls>',data,flags=re.S)
    code=b'<BkTxCd><Domn><Cd>ACMT</Cd><Fmly><Cd>MCOP</Cd><SubFmlyCd>INTR</SubFmlyCd></Fmly></Domn><Prtry><Cd>6607</Cd><Issr>ASNBANK</Issr></Prtry></BkTxCd>'
    return data.replace(b'<Sts>',code+b'<Sts>').replace(b'DBIT',b'CRDT').replace(b'2026-09-01',date.encode())


class EventRecognitionTests(unittest.TestCase):
    categories=[dict(id='income',code='inkomen',parent_id=None,transaction_type='INCOME'),
                dict(id='interest',code='inkomen_rente',parent_id='income',transaction_type='INCOME')]

    def setUp(self):
        self.payload=asdict(parse(rent_xml()).entries[0])
        self.row=dict(id='synthetic',amount='12.34',currency='EUR',transaction_type='UNKNOWN',
                      account_id='synthetic-account',private_data=self.payload)

    def test_empty_party_and_details_use_bank_namespace_and_code(self):
        rule=events.match(self.row,self.payload)
        self.assertEqual('asn-interest-6607',rule['id'])
        self.assertFalse(self.payload['counterparty'])
        self.assertEqual(('6607','ASNBANK'),tuple(self.payload['bank_codes'][0][k] for k in ('proprietary','issuer')))
        infer=Mock(side_effect=AssertionError('No LLM'))
        with patch.object(local,'decrypt',side_effect=lambda v:v):
            result=local.decide(self.row,[],self.categories,({},{}),infer,allow_llm=False)
        self.assertEqual(('inkomen_rente','asn-interest-6607'),(result['subcategory_code'],result['rule']))
        infer.assert_not_called()

    def test_unknown_conflicting_direction_currency_and_reversal_abstain(self):
        code=self.payload['bank_codes'][0]
        for changed in [{'issuer':'OTHER'},{'issuer':''},{'proprietary':'9999'},{'family':'MDOP'}, {'domain':'PMNT'}]:
            self.assertIsNone(events.match(self.row,{**self.payload,'bank_codes':[{**code,**changed}]}))
        for changed in [dict(amount='-12.34'),dict(amount='0'),dict(currency='USD')]:
            self.assertIsNone(events.match({**self.row,**changed},self.payload))
        for changed in [dict(bank_codes=[]),dict(reversal='TRUE'),dict(reversal='UNKNOWN'),dict(details=[{},{}]),
                        dict(bank_codes=[code,{**code,'proprietary':'6606'}])]:
            self.assertIsNone(events.match(self.row,{**self.payload,**changed}))

    def test_owner_and_active_category_guards(self):
        self.assertIsNone(events.choice({**self.row,'confirmed':True},self.payload,self.categories))
        self.assertIsNone(events.choice(self.row,self.payload,self.categories[:1]))
        self.assertIsNone(events.choice(self.row,self.payload,[self.categories[0],{**self.categories[1],'active':False}]))
        self.assertIsNone(events.choice(self.row,self.payload,[self.categories[0],{**self.categories[1],'parent_id':'other'}]))
        rule=events.match(self.row,self.payload)
        self.assertEqual('manual_conflict',events.preview_status({**self.row,'confirmed':True,'category_code':'other'},rule))
        self.assertEqual('eligible',events.preview_status(self.row,rule))

    def test_legacy_bank_fallback_does_not_bypass_catalogue_checks(self):
        code=self.payload['bank_codes'][0]
        for change in ({'issuer':'OTHER'},{'family':'MDOP'}):
            payload={**self.payload,'bank_codes':[{**code,**change}]}
            row={**self.row,'transaction_type':'INCOME','classification_source':'RULE',
                 'rule_version':'bank-type-v1:interest_received','private_data':payload}
            with patch.object(local,'decrypt',side_effect=lambda v:v):
                self.assertIsNone(local.decide(row,[],self.categories,({},{}),Mock(side_effect=AssertionError('No LLM')),allow_llm=False))

    def test_historical_encrypted_evidence_and_conflicting_sources(self):
        cur=Mock();cur.fetchall.return_value=[dict(transaction_id='synthetic',private_data=dict(codes=self.payload['bank_codes'],reversal='false'))]
        row={**self.row,'private_data':{**self.payload,'bank_codes':[]}}
        with patch.object(events,'decrypt',side_effect=lambda v:v):
            payload=events.hydrate(cur,row,row['private_data'])
        self.assertIsNotNone(events.match(row,payload))
        cur.fetchall.return_value.append(dict(transaction_id='synthetic',private_data=dict(codes=[{'issuer':'OTHER','proprietary':'6607'}])))
        with patch.object(events,'decrypt',side_effect=lambda v:v):
            payload=events.hydrate(cur,row,row['private_data'])
        self.assertIsNone(events.match(row,payload))


if __name__=='__main__':unittest.main()
