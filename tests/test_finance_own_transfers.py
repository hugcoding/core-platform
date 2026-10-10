import unittest
from unittest.mock import patch, Mock
from core.finance import own_transfers as transfers
from core.finance import local_classification as local


class OwnTransferTests(unittest.TestCase):
    categories=[dict(code='overboekingen',id='transfer',parent_id=None,transaction_type='TRANSFER')]

    def setUp(self):
        self.hash=patch('core.finance.own_transfers.fingerprint',side_effect=lambda _,v:v)
        self.hash.start();self.addCleanup(self.hash.stop)
        self.scope=({'a':'g','b':'g','c':'h','d':None}, {'NLKNOWN':'b','NLOTHER':'c','NLSELF':'a'})
        self.payload=dict(counteraccount='nl known',counterparty='Imported name',description='',details=[{}])
        self.target=dict(account_id='a',amount=-4500,currency='EUR',transaction_type='UNKNOWN',private_data=self.payload)

    def test_known_counteraccount_both_directions_without_pair_or_llm(self):
        for amount in [-4500,4500]:
            self.assertEqual('TRANSFER',transfers.decide({**self.target,'amount':amount},self.payload,self.categories,self.scope)['transaction_type'])
        infer=Mock()
        with patch.object(local,'decrypt',side_effect=lambda v:v),patch.object(local,'identity',return_value=None):
            choice=local.decide(self.target,[],self.categories,self.scope,infer,allow_llm=False)
        infer.assert_not_called();self.assertEqual('known_account_transfer',choice['rule'])

    def test_unknown_self_aggregate_reversal_and_bank_purchase_abstain(self):
        for payload in [dict(counteraccount=''),dict(counteraccount='UNKNOWN'),dict(counteraccount='NLSELF'),
                {**self.payload,'details':[{},{}]}, {**self.payload,'reversal':'YES'}]:
            self.assertIsNone(transfers.decide(self.target,payload,self.categories,self.scope))
        for kind in ['EXPENSE','CORRECTION','INCOME']:
            self.assertIsNone(transfers.decide({**self.target,'transaction_type':kind,'classification_source':'RULE'},self.payload,self.categories,self.scope))
        for cats in [[],[{**self.categories[0],'active':False}],[{**self.categories[0],'transaction_type':'EXPENSE'}]]:
            self.assertIsNone(transfers.decide(self.target,self.payload,cats,self.scope))

    def test_current_groups_labels_and_bank_payload_unchanged(self):
        accounts=[dict(id='b',label='Spaarrekening'),dict(id='c',label='Kind')]
        groups=[dict(id='g',name='Privé'),dict(id='h',name='Kind')]
        row={**self.target,'transaction_type':'TRANSFER'}
        info=transfers.display(row,self.payload,self.scope,accounts,groups)
        self.assertEqual(('internal','Spaarrekening'),(info['own_transfer_scope'],info['counter_account_label']))
        other={**self.payload,'counteraccount':'NLOTHER'}
        info=transfers.display(row,other,self.scope,accounts,groups)
        self.assertEqual(('between_groups','Privé','Kind'),(info['own_transfer_scope'],info['source_group'],info['destination_group']))
        credit=transfers.display({**row,'amount':4500},other,self.scope,accounts,groups)
        self.assertEqual(('Kind','Privé'),(credit['source_group'],credit['destination_group']))
        unknown=({'a':None,'b':'g'},self.scope[1])
        self.assertEqual('unassigned',transfers.display(row,self.payload,unknown,accounts,groups)['own_transfer_scope'])
        self.assertNotIn('own_transfer_scope',transfers.display(self.target,self.payload,self.scope,accounts,groups))
        self.assertEqual('Imported name',self.payload['counterparty'])


if __name__=='__main__':unittest.main()
