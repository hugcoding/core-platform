import unittest
from unittest.mock import Mock,patch
from core.finance import income_patterns as patterns,local_classification as local


class IncomePatternTests(unittest.TestCase):
    categories=[dict(id='income',code='inkomen',parent_id=None,transaction_type='INCOME'),
                dict(id='salary',code='inkomen_salaris',parent_id='income',transaction_type='INCOME'),
                dict(id='interest',code='inkomen_rente',parent_id='income',transaction_type='INCOME')]

    def row(self,text='Salaris Periode 7-2026 Naomi',**changes):
        return dict(account_id='a',amount=405.17,currency='EUR',transaction_type='UNKNOWN',
                    private_data=dict(description=text,counterparty='Synthetic Employer B.V.',counteraccount='NLKNOWN'),**changes)

    def classify(self,row,examples=(),categories=None):
        infer=Mock(side_effect=AssertionError('No inference'))
        with patch.object(local,'decrypt',side_effect=lambda v:v),patch.object(local,'identity',return_value=None),patch('core.finance.own_transfers.fingerprint',return_value='synthetic'):
            choice=local.decide(row,list(examples),categories or self.categories,({},{}),infer,allow_llm=False)
        infer.assert_not_called();return choice

    def test_salary_changes_month_amount_and_split_payment(self):
        seed=self.row();key=patterns.key(seed,seed['private_data'])
        for text,amount in [('Salaris Juni 2025',665.04),('Salaris Periode 8-2026',216.67),('Loon september 2026',50)]:
            row=self.row(text);row['amount']=amount
            self.assertEqual(key,patterns.key(row,row['private_data']))
            self.assertEqual(('INCOME','inkomen_salaris'),tuple(self.classify(row)[k] for k in ['transaction_type','subcategory_code']))

    def test_owner_pattern_wins_and_conflicts_abstain(self):
        seed=self.row('Salaris Juni 2025');seed.update(payload=seed['private_data'],review_id='owner',transaction_type='INCOME',category_code='inkomen',subcategory_code='inkomen_rente',merchant_id='owner-merchant')
        choice=self.classify(self.row(),[seed])
        self.assertEqual(('MERCHANT','owner',patterns.METHOD,'inkomen_rente'),tuple(choice[k] for k in ['source','seed','method','subcategory_code']))
        self.assertIsNone(self.classify(self.row(),[seed,{**seed,'subcategory_code':'inkomen_salaris'}]))

    def test_no_cross_account_currency_employer_or_payment_purpose(self):
        row=self.row();key=patterns.key(row,row['private_data'])
        for changed in [{**row,'account_id':'other'},{**row,'currency':'USD'},
                        {**row,'private_data':{**row['private_data'],'counterparty':'Other company'}},
                        {**row,'private_data':{**row['private_data'],'counteraccount':'OTHER'}}]:
            self.assertNotEqual(key,patterns.key(changed,changed['private_data']))
        for text in ['Onkostenvergoeding juli','Salaris correctie','salaris terugbetaling','betaling loonheffing']:
            other=self.row(text);self.assertIsNone(patterns.key(other,other['private_data']))
        for changes in [dict(amount=-50),dict(transaction_type='CORRECTION')]:
            self.assertIsNone(patterns.key({**row,**changes},row['private_data']))
        for changes in [dict(details=[{},{}]),dict(reversal='YES')]:
            self.assertIsNone(patterns.key(row,{**row['private_data'],**changes}))

    def test_interest_pattern_ignores_dates_and_missing_bank_name(self):
        row=self.row('Rente over positief saldo tot 01-04-26');row['private_data']['counterparty']=''
        seed=self.row('Rente over positief saldo tot 01-03-26');seed.update(payload=seed['private_data'],review_id='owner',transaction_type='INCOME',category_code='inkomen',subcategory_code='inkomen_rente',merchant_id='bank')
        self.assertEqual('owner',self.classify(row,[seed])['seed'])
        self.assertEqual('inkomen_rente',self.classify(row)['subcategory_code'])

    def test_refinement_only_same_category_and_type_not_owner_or_specific(self):
        row=self.row(category_code='inkomen',classification_source='RULE');row['transaction_type']='INCOME'
        choice=self.classify(row)
        self.assertTrue(patterns.refines(row,choice))
        for other in [{**row,'confirmed':True},{**row,'subcategory_code':'inkomen_rente'},
                      {**row,'category_code':'other'},{**row,'transaction_type':'EXPENSE'}]:
            self.assertFalse(patterns.refines(other,choice))
        self.assertFalse(patterns.refines(row,{**choice,'source':'AI'}))
        self.assertFalse(patterns.refines(row,{**choice,'subcategory_code':None}))

    def test_inactive_or_reparented_categories_do_not_get_guessed(self):
        row=self.row()
        for child in [{**self.categories[1],'active':False},{**self.categories[1],'parent_id':'other'}]:
            self.assertIsNone(patterns.default(row,row['private_data'],[self.categories[0],child]))


if __name__=='__main__':unittest.main()
