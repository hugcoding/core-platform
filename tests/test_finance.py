"""Synthetic-only parser, privacy, API and real PostgreSQL integration tests."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from cryptography.fernet import Fernet
from core.finance.camt import parse, NS, ImportErrorCode
from core.finance.privacy import protected_path, deny_generic_access

IBAN='NL91ABNA0417164300'  # Public format example; all transactions are fabricated.


def sample(message='synthetic',count=1,description='SYNTHETIC CANARY',amount='12.34'):
    entry=f'''<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts>
    <BookgDt><Dt>2026-09-01</Dt></BookgDt><ValDt><Dt>2026-09-01</Dt></ValDt>
    <NtryDtls><TxDtls><Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>
    <RltdPties><Cdtr><Nm>Synthetische winkel</Nm></Cdtr></RltdPties>
    <RmtInf><Ustrd>{description}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>'''
    return f'''<?xml version="1.0" encoding="UTF-8"?><Document xmlns="{NS}"><BkToCstmrStmt>
    <GrpHdr><MsgId>{message}</MsgId></GrpHdr><Stmt><Id>synthetic-statement</Id><Acct><Id><IBAN>{IBAN}</IBAN></Id></Acct>
    {entry*count}</Stmt></BkToCstmrStmt></Document>'''.encode()


class ParserTests(unittest.TestCase):
    def test_decimal_direction_and_locator(self):
        p=parse(sample(count=2))
        self.assertEqual(['-12.34','-12.34'],[e.amount for e in p.entries])
        self.assertEqual(['stmt:1/entry:1','stmt:1/entry:2'],[e.locator for e in p.entries])
        self.assertEqual(0,p.balances_checked)

    def test_invalid_and_unsafe_are_codes_only(self):
        for data,code in [(b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///private">]><x/>','unsafe_xml'),
                          (sample().replace(NS.encode(),b'wrong'),'unsupported_namespace'),
                          (sample(amount='NaN'),'invalid_amount'),
                          (sample().replace(b'2026-09-01',b'2026-02-30'),'invalid_date')]:
            with self.assertRaises(ImportErrorCode) as err: parse(data)
            self.assertEqual(code,str(err.exception))

    def test_balances(self):
        balance=lambda kind,amount: f'<Bal><Tp><CdOrPrtry><Cd>{kind}</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>CRDT</CdtDbtInd></Bal>'
        source=sample().replace(b'</Acct>',('</Acct>'+balance('OPBD','20.00')+balance('CLBD','7.66')).encode())
        self.assertEqual(1,parse(source).balances_checked)
        with self.assertRaisesRegex(ImportErrorCode,'balance_mismatch'): parse(source.replace(b'7.66',b'7.67'))

    def test_reversal_does_not_double_negate_and_details_not_double_counted(self):
        data=sample().replace(b'<Sts>',b'<RvslInd>YES</RvslInd><Sts>')
        self.assertEqual('-12.34',parse(data).entries[0].amount)
        detail=b'<TxDtls><RmtInf><Ustrd>second detail</Ustrd></RmtInf></TxDtls>'
        p=parse(sample().replace(b'</NtryDtls>',detail+b'</NtryDtls>'))
        self.assertEqual(1,len(p.entries));self.assertEqual(2,len(p.entries[0].details))

    def test_privacy_boundary(self):
        self.assertTrue(protected_path('/volume1/data/import/finance/a.xml'))
        self.assertFalse(protected_path('/volume1/data/import/finance-other/a.xml'))
        with self.assertRaisesRegex(PermissionError,'finance_source_protected'):
            deny_generic_access('/volume1/data/import/finance/a.xml')

    def test_generic_privacy_classification(self):
        from core.organization.privacy_classification import propose_privacy
        result=propose_privacy({'path':'/volume1/data/import/finance/a.xml'})
        self.assertEqual('high',result['classification'])
        self.assertFalse(result['external_llm_content_allowed'])

    def test_resource_gate_fails_closed_and_respects_execution(self):
        from unittest.mock import MagicMock
        from finance_worker import gate
        conn=MagicMock();client=MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value={'busy':True,'sessions':0}
        with patch('finance_worker.host_resources',return_value={'cpu_load_percent':0,'available_memory_mib':9999}),patch('finance_worker.stream_lag',return_value=0):
            self.assertEqual('controlled_execution_priority',gate(conn,client))
        with patch('finance_worker.host_resources',return_value={'cpu_load_percent':99,'available_memory_mib':9999}):
            self.assertEqual('waiting_for_cpu',gate(conn,client))
        with patch('finance_worker.host_resources',return_value={'cpu_load_percent':0,'available_memory_mib':1}):
            self.assertEqual('waiting_for_memory',gate(conn,client))


@unittest.skipUnless(os.getenv('DB_NAME')=='core_finance_test','isolated PostgreSQL required')
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg2
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from dashboard.finance import router,finance_boundary
        cls.temp=tempfile.TemporaryDirectory(); cls.root=Path(cls.temp.name)
        cls.secrets=cls.root/'secret.json'
        cls.secrets.write_text(json.dumps({'data_key':Fernet.generate_key().decode(),'session_key':Fernet.generate_key().decode(),
            'identity_key':'synthetic-key','access_hash':hashlib.sha256(b'synthetic-access').hexdigest()}))
        os.environ['CORE_FINANCE_SECRET_FILE']=str(cls.secrets);os.environ['CORE_FINANCE_ENABLED']='true'
        cls.admin=psycopg2.connect(host=os.environ['DB_HOST'],port=os.getenv('DB_PORT','5432'),
            user=os.environ['DB_USER'],password=os.environ['DB_PASS'],dbname='core_finance_test')
        cls.admin.autocommit=True
        with cls.admin.cursor() as cur:
            cur.execute('''CREATE TABLE public.folders(id serial PRIMARY KEY,path text UNIQUE);
            CREATE TABLE public.files(id serial PRIMARY KEY,folder_id integer REFERENCES folders(id),filename text,path text UNIQUE,
            extension text,size_bytes bigint,mime_type text,source text,content_sha256 text);
            CREATE VIEW public.v_controlled_execution_batch_progress AS SELECT NULL::uuid AS id,NULL::text AS batch_status WHERE false;''')
            up=Path('database/migrations/20260916_add_finance_mvp.sql').read_text()
            down=Path('database/migrations/rollback/20260916_add_finance_mvp.sql').read_text()
            cur.execute(up);cur.execute(down);cur.execute(up)
            names_up=Path('database/migrations/20260916_add_finance_account_names.sql').read_text()
            names_down=Path('database/migrations/rollback/20260916_add_finance_account_names.sql').read_text()
            cur.execute(names_up);cur.execute(names_down);cur.execute(names_up)
            suggestions_up=Path('database/migrations/20260917_add_finance_suggestion_audit.sql').read_text()
            suggestions_down=Path('database/migrations/rollback/20260917_add_finance_suggestion_audit.sql').read_text()
            cur.execute(suggestions_up);cur.execute(suggestions_down);cur.execute(suggestions_up)
            classification_up=Path('database/migrations/20260918_add_finance_classification.sql').read_text(encoding='utf-8')
            classification_down=Path('database/migrations/rollback/20260918_add_finance_classification.sql').read_text(encoding='utf-8')
            cur.execute(classification_up);cur.execute(classification_down);cur.execute(classification_up)
            groups_up=Path('database/migrations/20260923_add_finance_wealth_groups.sql').read_text(encoding='utf-8')
            groups_down=Path('database/migrations/rollback/20260923_add_finance_wealth_groups.sql').read_text(encoding='utf-8')
            cur.execute(groups_up);cur.execute(groups_down);cur.execute(groups_up)
            balances_up=Path('database/migrations/20260923_add_finance_bank_balances.sql').read_text(encoding='utf-8')
            balances_down=Path('database/migrations/rollback/20260923_add_finance_bank_balances.sql').read_text(encoding='utf-8')
            cur.execute(balances_up);cur.execute(balances_down);cur.execute(balances_up)
            refs_up=Path('database/migrations/20260924_add_finance_bank_references.sql').read_text(encoding='utf-8')
            refs_down=Path('database/migrations/rollback/20260924_add_finance_bank_references.sql').read_text(encoding='utf-8')
            cur.execute(refs_up);cur.execute(refs_down);cur.execute(refs_up)
        app=FastAPI();app.middleware('http')(finance_boundary);app.include_router(router)
        cls.client=TestClient(app);cls.client.headers['origin']='http://testserver'
        response=cls.client.post('/api/v1/finance/session',json={'code':'synthetic-access'})
        assert response.status_code==200

    @classmethod
    def tearDownClass(cls):
        cls.admin.close(); cls.temp.cleanup()

    def import_file(self,data,name=None):
        from core.finance.store import connection,import_bytes
        path=self.root/(name or str(uuid.uuid4())+'.xml')
        with connection(worker=True) as conn:
            return import_bytes(conn,path,data)

    def test_90_overview_import_dates_survive_rollback_and_duplicates(self):
        from tests.test_finance_bank_references import numbered
        marker=str(uuid.uuid4())
        self.import_file(numbered(ref=marker,message=marker,n=98765))
        before=self.client.get('/api/v1/finance/data').json()
        batch=before['imports'][0]
        self.assertIsNotNone(batch['imported_at'])
        self.assertIsNone(batch['rolled_back_at'])
        self.assertEqual('2026-09-01',batch['last_transaction_date'])
        account=before['accounts'][-1]
        self.assertIn('2026-09',before['periods_by_account'][account['id']])
        self.import_file(numbered(ref=marker,message=marker+'-copy',n=98765))
        duplicate=self.client.get('/api/v1/finance/data').json()['imports'][0]
        self.assertEqual('2026-09-01',duplicate['last_transaction_date'])
        self.assertEqual(200,self.client.post('/api/v1/finance/imports/'+duplicate['id']+'/rollback',json={'confirm':True}).status_code)
        after=next(b for b in self.client.get('/api/v1/finance/data').json()['imports'] if b['id']==duplicate['id'])
        self.assertIsNotNone(after['rolled_back_at'])
        self.assertEqual(duplicate['imported_at'],after['imported_at'])
        self.assertEqual('2026-09-01',after['last_transaction_date'])

    def test_01_parallel_replay_and_duplicate_multiplicity(self):
        source=sample(count=2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda name:self.import_file(source,name),['copy-a.xml','copy-b.xml']))
        self.assertEqual(1,sum(not r['replay'] for r in results))
        data=self.client.get('/api/v1/finance/data').json()
        self.assertEqual('2',data['totals']['total'])
        self.assertEqual('-24.68',data['totals']['net'])
        second=self.import_file(sample(message='new-download',count=2))
        self.assertEqual('partial',second['status']);self.assertEqual(2,second['unresolved'])
        self.assertEqual('2',self.client.get('/api/v1/finance/data').json()['totals']['total'])

    def test_02_review_and_rollback_keep_history_and_shared_evidence(self):
        data=self.client.get('/api/v1/finance/data').json();tid=data['transactions'][0]['id']
        request={'key':str(uuid.uuid4()),'category':'boodschappen','previous':None}
        endpoint='/api/v1/finance/transactions/'+tid+'/category'
        self.assertEqual(200,self.client.post(endpoint,json=request).status_code)
        self.assertEqual(200,self.client.post(endpoint,json=request).status_code)
        self.assertEqual(409,self.client.post(endpoint,json={**request,'category':'overig'}).status_code)
        self.assertEqual(409,self.client.post(endpoint,json={**request,'key':str(uuid.uuid4())}).status_code)
        pending=self.client.get('/api/v1/finance/unresolved').json()['records']
        for i,r in enumerate(pending):
            self.assertEqual(200,self.client.post('/api/v1/finance/unresolved/'+r['id'],json={
                'key':str(uuid.uuid4()),'decision':'same','transaction_id':data['transactions'][i]['id']}).status_code)
        imports=self.client.get('/api/v1/finance/data').json()['imports']
        first=imports[-1]['id']
        self.assertEqual(200,self.client.post('/api/v1/finance/imports/'+first+'/rollback',json={'confirm':True}).status_code)
        self.assertEqual('2',self.client.get('/api/v1/finance/data').json()['totals']['total'])
        self.assertTrue(self.import_file(sample(count=2))['replay'])
        second=imports[0]['id']
        self.assertEqual(200,self.client.post('/api/v1/finance/imports/'+second+'/rollback',json={'confirm':True}).status_code)
        self.assertEqual('0',self.client.get('/api/v1/finance/data').json()['totals']['total'])
        with self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM finance.finance_transactions');self.assertEqual(2,cur.fetchone()[0])

    def test_03_sources_encrypted_and_api_locked(self):
        from fastapi.testclient import TestClient
        anonymous=TestClient(self.client.app)
        self.assertEqual(401,anonymous.get('/api/v1/finance/data').status_code)
        self.assertEqual(403,anonymous.post('/api/v1/finance/session',json={'code':'synthetic-access'}).status_code)
        with self.admin.cursor() as cur:
            cur.execute('SELECT id,original_ciphertext FROM finance.finance_source_documents LIMIT 1')
            sid,value=cur.fetchone();self.assertNotIn('SYNTHETIC CANARY',value)
        self.assertEqual(401,anonymous.get('/api/v1/finance/sources/'+str(sid)).status_code)
        response=self.client.get('/api/v1/finance/sources/'+str(sid))
        self.assertEqual(sample(count=2),response.content)
        self.assertEqual('no-store',response.headers['cache-control'])

    def test_04_db_protection_and_populated_rollback(self):
        import psycopg2
        from core.finance.store import connection
        for statement in ['DELETE FROM finance.finance_transactions','UPDATE finance.finance_accounts SET private_data=\'x\'',
                          'TRUNCATE finance.finance_import_events']:
            with self.assertRaises(psycopg2.Error):
                with connection(worker=True) as conn,conn.cursor() as cur:cur.execute(statement)
        with self.assertRaises(psycopg2.Error):
            with self.admin.cursor() as cur:
                cur.execute(Path('database/migrations/rollback/20260916_add_finance_mvp.sql').read_text())
        with self.admin.cursor() as cur:cur.execute('ROLLBACK')
        with self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM finance.finance_source_documents');self.assertGreater(cur.fetchone()[0],0)

    def test_05_rejected_is_auditable_and_idempotent(self):
        source=sample().replace(NS.encode(),b'unsupported')
        result=self.import_file(source)
        self.assertEqual('rejected',result['status']);self.assertTrue(self.import_file(source)['replay'])

    def test_06_failed_commit_publishes_nothing(self):
        from core.finance.store import connection,import_bytes
        with self.assertRaises(RuntimeError):
            with connection(worker=True) as conn:
                import_bytes(conn,self.root/'crash.xml',sample(description='SYNTHETIC UNIQUE CRASH'))
                raise RuntimeError('synthetic crash')
        result=self.import_file(sample(description='SYNTHETIC UNIQUE CRASH'))
        self.assertFalse(result['replay']);self.assertEqual('imported',result['status'])

    def test_07_admission_lock_and_source_constraints(self):
        import psycopg2
        from core.finance.store import connection,ADMISSION_LOCK
        with connection(worker=True) as first,connection(worker=True) as second:
            with first.cursor() as cur:cur.execute('SELECT pg_advisory_xact_lock(%s)',(ADMISSION_LOCK,))
            with second.cursor() as cur:
                cur.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(ADMISSION_LOCK,))
                self.assertFalse(cur.fetchone()['acquired'])
        with self.assertRaises(psycopg2.Error):
            with connection(worker=True) as conn,conn.cursor() as cur:
                cur.execute('''INSERT INTO finance.finance_transactions(record_id,account_id,booking_date,amount,currency,fingerprint,private_data)
                    SELECT r.id,r.account_id,'2026-09-01',1,'EUR',r.fingerprint,r.private_data FROM finance.finance_import_records r
                    WHERE NOT EXISTS(SELECT 1 FROM finance.finance_transactions t WHERE t.record_id=r.id) LIMIT 1''')


    def test_08_sorting_covers_all_pages_and_validates_input(self):
        template=sample().decode().replace('2026-09-01','2026-08-01')
        start,end=template.index('<Ntry>'),template.index('</Ntry>')+len('</Ntry>')
        entries=[]
        for i in range(105):
            entry=template[start:end].replace('12.34',str(i+1)+'.00')
            entry=entry.replace('SYNTHETIC CANARY',f'Sorting {104-i:03d}')
            entry=entry.replace('Synthetische winkel',f'Synthetic party {i:03d}')
            entries.append(entry)
        self.import_file((template[:start]+''.join(entries)+template[end:]).encode())
        from decimal import Decimal
        for field in ('booking_date','amount','counterparty','description','category'):
            for direction in ('asc','desc'):
                responses=[self.client.get(f'/api/v1/finance/data?month=2026-08&sort={field}&direction={direction}&page={page}') for page in (0,1)]
                self.assertTrue(all(r.status_code==200 for r in responses))
                rows=[row for response in responses for row in response.json()['transactions']]
                self.assertEqual(105,len(rows));self.assertEqual(105,len({r['id'] for r in rows}))
                categories={c['code']:c['label'] for c in responses[0].json()['categories']}
                values=[Decimal(r['amount']) if field=='amount' else
                    (categories.get(r['category_code'],'Nog te categoriseren') if field=='category' else r[field]).casefold() for r in rows]
                self.assertEqual(sorted(values,reverse=direction=='desc'),values)
                if field=='booking_date':
                    self.assertEqual([Decimal(-i) for i in range(1,106)],[Decimal(r['amount']) for r in rows])
        for query in ('sort=amount;DROP TABLE finance.finance_transactions','direction=desc nulls first'):
            self.assertEqual(422,self.client.get('/api/v1/finance/data',params=dict([query.split('=',1)])).status_code)


    def test_09_date_ties_follow_source_and_numeric_statement_order(self):
        from decimal import Decimal
        template=sample().decode().replace('2026-09-01','2026-07-01')
        start,end=template.index('<Stmt>'),template.index('</Stmt>')+len('</Stmt>')
        statements=[template[start:end].replace('12.34',f'{i}.00') for i in range(1,13)]
        self.import_file((template[:start]+''.join(statements)+template[end:]).encode(),'z-first.xml')
        self.import_file(template.replace('12.34','99.00').encode(),'a-second.xml')
        self.import_file(template.replace('2026-07-01','2026-07-02').replace('12.34','100.00').encode(),'next-day.xml')
        source_order=[Decimal(-i) for i in range(1,13)]+[Decimal(-99)]
        for direction in ('asc','desc'):
            response=self.client.get(f'/api/v1/finance/data?month=2026-07&sort=booking_date&direction={direction}')
            self.assertEqual(200,response.status_code)
            expected=source_order+[Decimal(-100)] if direction=='asc' else [Decimal(-100)]+source_order
            self.assertEqual(expected,[Decimal(r['amount']) for r in response.json()['transactions']])


    def test_10_account_names_are_private_auditable_and_survive_reimport(self):
        import psycopg2
        from core.finance.store import connection
        account=self.client.get('/api/v1/finance/data').json()['accounts'][0]
        aid=account['id']; endpoint='/api/v1/finance/accounts/'+aid+'/name'
        payload={'name':'SYNTHETIC PRIVATE LABEL','previous':None,'key':str(uuid.uuid4())}
        self.assertEqual(200,self.client.post(endpoint,json=payload).status_code)
        self.assertEqual(200,self.client.post(endpoint,json=payload).status_code)
        self.assertEqual(409,self.client.post(endpoint,json={**payload,'name':'different'}).status_code)
        renamed=self.client.get('/api/v1/finance/data').json()['accounts'][0]
        self.assertEqual(payload['name'],renamed['display_name'])
        self.assertIn(IBAN[-4:],renamed['label']);self.assertNotIn(IBAN,renamed['label'])
        self.assertNotIn('iban',renamed)
        self.assertEqual(409,self.client.post(endpoint,json={**payload,'key':str(uuid.uuid4())}).status_code)
        self.import_file(sample(count=2),'name-replay.xml')
        self.assertEqual(payload['name'],self.client.get('/api/v1/finance/data').json()['accounts'][0]['display_name'])
        with self.admin.cursor() as cur:
            cur.execute('SELECT private_data FROM finance.finance_account_name_events WHERE account_id=%s',(aid,))
            history=cur.fetchall();self.assertEqual(1,len(history));self.assertNotIn(payload['name'],history[0][0])
        clear={'name':'','previous':renamed['name_event_id'],'key':str(uuid.uuid4())}
        self.assertEqual(200,self.client.post(endpoint,json=clear).status_code)
        restored=self.client.get('/api/v1/finance/data').json()['accounts'][0]
        self.assertIsNone(restored['display_name']);self.assertEqual(account['label'],restored['label'])
        for sql in ["UPDATE finance.finance_account_name_events SET actor='changed'",
                    'DELETE FROM finance.finance_account_name_events','TRUNCATE finance.finance_account_name_events']:
            with self.assertRaises(psycopg2.Error):
                with connection() as conn,conn.cursor() as cur:cur.execute(sql)
        with self.assertRaises(psycopg2.Error):
            with self.admin.cursor() as cur:
                cur.execute(Path('database/migrations/rollback/20260916_add_finance_account_names.sql').read_text())
        with self.admin.cursor() as cur:cur.execute('ROLLBACK')
        with self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM finance.finance_account_name_events WHERE account_id=%s',(aid,))
            self.assertEqual(2,cur.fetchone()[0])

    def test_11_account_name_access_validation_and_concurrent_review(self):
        from fastapi.testclient import TestClient
        from core.finance.crypto import encrypt,fingerprint
        with self.admin.cursor() as cur:
            cur.execute("""INSERT INTO finance.finance_accounts(identity_key,private_data)
                VALUES (%s,%s) RETURNING id""",(fingerprint('account-v1','synthetic-other'),encrypt({'iban':IBAN,'label':'Synthetic other'})))
            aid=str(cur.fetchone()[0])
        endpoint='/api/v1/finance/accounts/'+aid+'/name'
        payload={'name':'Synthetic concurrent','previous':None,'key':str(uuid.uuid4())}
        anonymous=TestClient(self.client.app)
        self.assertEqual(401,anonymous.post(endpoint,json=payload,headers={'Origin':'http://testserver'}).status_code)
        self.assertEqual(403,self.client.post(endpoint,json=payload,headers={'Origin':'http://other.invalid'}).status_code)
        for value in [None,{},'x'*81,'line\nbreak','hidden\u202ename']:
            self.assertEqual(422,self.client.post(endpoint,json={**payload,'name':value}).status_code)
        self.assertEqual(404,self.client.post('/api/v1/finance/accounts/'+str(uuid.uuid4())+'/name',json=payload).status_code)
        def submit(key):
            client=TestClient(self.client.app);client.cookies.update(self.client.cookies)
            return client.post(endpoint,json={**payload,'key':key},headers={'Origin':'http://testserver'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(submit,[str(uuid.uuid4()),str(uuid.uuid4())]))
        self.assertEqual([200,409],sorted(statuses))



    def test_12_year_and_inclusive_date_range(self):
        template=sample(description='SYNTHETIC PERIOD').decode()
        start,end=template.index('<Ntry>'),template.index('</Ntry>')+len('</Ntry>')
        dates=['2023-12-31','2024-01-01','2024-02-28','2024-02-29','2024-03-01','2024-12-31','2025-01-01']
        entries=[template[start:end].replace('2026-09-01',day).replace('12.34',f'{i}.00') for i,day in enumerate(dates,1)]
        self.import_file((template[:start]+''.join(entries)+template[end:]).encode())
        for params,count,net in [({'year':'2024'},5,'-20.00'),({'month':'2024-02'},2,'-7.00'),
            ({'date_from':'2024-02-28','date_to':'2024-03-01'},3,'-12.00'),
            ({'date_from':'2024-02-29','date_to':'2024-02-29'},1,'-4.00'),
            ({'date_from':'2023-12-31','date_to':'2024-01-01'},2,'-3.00')]:
            response=self.client.get('/api/v1/finance/data',params=params)
            self.assertEqual(200,response.status_code);data=response.json()
            self.assertEqual(count,len(data['transactions']));self.assertEqual(str(count),data['totals']['total'])
            self.assertEqual(net,data['totals']['net']);self.assertIn('2024',data['years'])
        empty=self.client.get('/api/v1/finance/data?year=2027').json()
        self.assertEqual('0',empty['totals']['total']);self.assertEqual([],empty['transactions'])
        for params in [{'year':'2024','month':'2024-01'},{'year':'0000'},{'date_from':'2024-01-01'},
            {'date_from':'2024-03-01','date_to':'2024-02-28'},{'year':'20xx'},
            {'date_from':'2023-02-29','date_to':'2023-03-01'},
            {'month':'2024-01','date_from':'2024-01-01','date_to':'2024-01-02'}]:
            self.assertEqual(422,self.client.get('/api/v1/finance/data',params=params).status_code)

    def test_13_period_filter_combines_with_account_sort_and_pages(self):
        template=sample(description='SYNTHETIC PERIOD PAGING').decode().replace('2026-09-01','2021-01-01')
        start,end=template.index('<Ntry>'),template.index('</Ntry>')+len('</Ntry>')
        entries=[template[start:end].replace('12.34',f'{i}.00') for i in range(1,106)]
        self.import_file((template[:start]+''.join(entries)+template[end:]).encode())
        aid=self.client.get('/api/v1/finance/data?year=2021').json()['transactions'][0]['account_id']
        for period in [{'year':'2021'},{'date_from':'2021-01-01','date_to':'2021-01-01'}]:
            rows=[]
            for page in (0,1):
                result=self.client.get('/api/v1/finance/data',params={**period,'account':aid,
                    'category':'uncategorized','sort':'amount','direction':'asc','page':page}).json()
                self.assertEqual('105',result['totals']['total']);rows.extend(result['transactions'])
            self.assertEqual(105,len({r['id'] for r in rows}))
            self.assertEqual([f'{-i}.00' for i in range(105,0,-1)],[r['amount'] for r in rows])


    def test_14_local_proposals_require_confirmation_and_preserve_evidence(self):
        def add(name,credit=False):
            data=sample(description=name).replace(b'2026-09-01',b'2020-01-01').replace(b'Synthetische winkel',b'')
            if credit:data=data.replace(b'<CdtDbtInd>DBIT',b'<CdtDbtInd>CRDT')
            self.import_file(data)
        for name in ('OVpay seed TEST001','www.ovpay02.01.2020 TEST002','MCC:4111 Apple Pay TEST003','OVpay existing TEST004'):
            add(name)
        add('OVpay credit TEST005',credit=True)
        rows=self.client.get('/api/v1/finance/data?year=2020').json()['transactions']
        seed=next(r for r in rows if r['description'].startswith('OVpay seed'))
        target=next(r for r in rows if r['description'].startswith('www.ovpay'))
        existing=next(r for r in rows if r['description'].startswith('OVpay existing'))
        for row in (seed,existing):
            self.assertEqual(200,self.client.post('/api/v1/finance/transactions/'+row['id']+'/category',
                json={'category':'vervoer','previous':None,'key':str(uuid.uuid4())}).status_code)
        route='/api/v1/finance/transactions/'+seed['id']+'/suggestions'
        response=self.client.get(route);self.assertEqual(200,response.status_code);proposal=response.json()
        self.assertEqual('ovpay',proposal['reason']);self.assertEqual('vervoer',proposal['category_code'])
        self.assertEqual([target['id']],[r['id'] for r in proposal['transactions']])
        self.assertEqual(1,proposal['total'])
        with self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM finance.finance_review_events WHERE transaction_id=%s',(target['id'],))
            self.assertEqual(0,cur.fetchone()[0])
        payload={'seed_transaction_id':seed['id'],'seed_review_id':proposal['seed_review_id'],
                 'previous':None,'key':str(uuid.uuid4())}
        accept='/api/v1/finance/transactions/'+target['id']+'/suggestion'
        self.assertEqual(200,self.client.post(accept,json=payload).status_code)
        self.assertEqual(200,self.client.post(accept,json=payload).status_code)
        with self.admin.cursor() as cur:
            cur.execute('SELECT category_code,source_review_id,suggestion_method FROM finance.finance_review_events WHERE transaction_id=%s',(target['id'],))
            events=cur.fetchall();self.assertEqual(1,len(events));self.assertEqual('vervoer',events[0][0])
            self.assertEqual(proposal['seed_review_id'],str(events[0][1]));self.assertEqual('local-merchant-v2',events[0][2])
        self.assertEqual(0,self.client.get(route).json()['total'])
        inherited=self.client.get('/api/v1/finance/transactions/'+target['id']+'/suggestions')
        self.assertEqual(200,inherited.status_code)
        self.assertTrue(inherited.json()['from_original_example'])
        self.assertEqual(seed['id'],inherited.json()['seed_transaction_id'])
        self.assertEqual(proposal['seed_review_id'],inherited.json()['seed_review_id'])

    def test_15_stale_conflicting_and_unauthorized_proposals(self):
        from fastapi.testclient import TestClient
        data=sample(description='OVpay later TEST006').replace(b'2026-09-01',b'2020-01-02').replace(b'Synthetische winkel',b'')
        self.import_file(data)
        rows=self.client.get('/api/v1/finance/data?year=2020').json()['transactions']
        seed=next(r for r in rows if r['description'].startswith('OVpay seed'))
        target=next(r for r in rows if r['description'].startswith('OVpay later'))
        route='/api/v1/finance/transactions/'+seed['id']+'/suggestions'
        proposal=self.client.get(route).json()
        self.assertEqual(401,TestClient(self.client.app).get(route).status_code)
        payload={'seed_transaction_id':seed['id'],'seed_review_id':proposal['seed_review_id'],'previous':None,'key':str(uuid.uuid4())}
        accept='/api/v1/finance/transactions/'+target['id']+'/suggestion'
        self.assertEqual(403,self.client.post(accept,json=payload,headers={'Origin':'http://other.invalid'}).status_code)
        self.assertEqual(200,self.client.post('/api/v1/finance/transactions/'+seed['id']+'/category',
            json={'category':'overig','previous':seed['review_id'],'key':str(uuid.uuid4())}).status_code)
        inherited=next(r for r in rows if r['description'].startswith('www.ovpay'))
        invalid=self.client.get('/api/v1/finance/transactions/'+inherited['id']+'/suggestions')
        self.assertEqual(409,invalid.status_code)
        self.assertEqual('suggestion_example_changed',invalid.json()['detail'])
        self.assertEqual('conflicting_examples',self.client.get(route).json()['reason'])
        self.assertEqual(0,self.client.get(route).json()['total'])
        self.assertEqual(409,self.client.post(accept,json=payload).status_code)
        with self.admin.cursor() as cur:
            cur.execute('SELECT category_code FROM finance.v_transactions WHERE id=%s',(target['id'],))
            self.assertIsNone(cur.fetchone()[0])
        latest=next(r for r in self.client.get('/api/v1/finance/data?year=2020').json()['transactions'] if r['id']==seed['id'])
        self.client.post('/api/v1/finance/transactions/'+seed['id']+'/category',
            json={'category':'vervoer','previous':latest['review_id'],'key':str(uuid.uuid4())})
        proposal=self.client.get(route).json();payload['seed_review_id']=proposal['seed_review_id']
        def submit(key):
            client=TestClient(self.client.app);client.cookies.update(self.client.cookies)
            return client.post(accept,json={**payload,'key':key},headers={'Origin':'http://testserver'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(submit,[str(uuid.uuid4()),str(uuid.uuid4())]))
        self.assertEqual([200,409],sorted(results))

    def test_16_suggestion_audit_rollback_refuses_history_and_inactive_source(self):
        import psycopg2
        with self.assertRaises(psycopg2.Error):
            with self.admin.cursor() as cur:
                cur.execute(Path('database/migrations/rollback/20260917_add_finance_suggestion_audit.sql').read_text())
        with self.admin.cursor() as cur:cur.execute('ROLLBACK')
        rows=self.client.get('/api/v1/finance/data?year=2020').json()['transactions']
        seed=next(r for r in rows if r['description'].startswith('OVpay seed'))
        sources=self.client.get('/api/v1/finance/transactions/'+seed['id']+'/sources').json()['sources']
        self.assertEqual(200,self.client.post('/api/v1/finance/imports/'+sources[0]['batch_id']+'/rollback',json={'confirm':True}).status_code)
        self.assertEqual(409,self.client.get('/api/v1/finance/transactions/'+seed['id']+'/suggestions').status_code)


    def test_17_bulk_selection_atomic_idempotent_and_audited(self):
        for name in ('bulk seed','bulk one','bulk two','bulk untouched'):
            data=sample(description=name).replace(b'2026-09-01',b'2019-01-01').replace(b'Synthetische winkel',b'Synthetic bulk merchant')
            data=data.replace(b'</RltdPties>',b'<CdtrAcct><Id><IBAN>NL91ABNA0417164300</IBAN></Id></CdtrAcct></RltdPties>')
            self.import_file(data)
        rows=self.client.get('/api/v1/finance/data?year=2019').json()['transactions']
        seed=next(r for r in rows if r['description']=='bulk seed')
        self.assertEqual(200,self.client.post('/api/v1/finance/transactions/'+seed['id']+'/category',
            json={'category':'vervoer','previous':None,'key':str(uuid.uuid4())}).status_code)
        proposal=self.client.get('/api/v1/finance/transactions/'+seed['id']+'/suggestions').json()
        targets=proposal['transactions'];self.assertEqual(3,len(targets))
        payload={'seed_transaction_id':seed['id'],'seed_review_id':proposal['seed_review_id'],
                 'key':str(uuid.uuid4()),'items':[{'id':t['id'],'previous':t['review_id']} for t in targets[:2]]}
        route='/api/v1/finance/suggestions/approve'
        from fastapi.testclient import TestClient
        self.assertEqual(401,TestClient(self.client.app).post(route,json=payload,headers={'Origin':'http://testserver'}).status_code)
        self.assertEqual(403,self.client.post(route,json=payload,headers={'Origin':'http://other.invalid'}).status_code)
        for items in ([],payload['items']*26,[payload['items'][0]]*2):
            self.assertEqual(422,self.client.post(route,json={**payload,'items':items}).status_code)
        stale={**payload,'items':[payload['items'][0],{**payload['items'][1],'previous':str(uuid.uuid4())}]}
        self.assertEqual(409,self.client.post(route,json=stale).status_code)
        with self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM finance.finance_review_events WHERE transaction_id IN (%s,%s)',tuple(t['id'] for t in targets[:2]))
            self.assertEqual(0,cur.fetchone()[0])
        for _ in range(2):
            response=self.client.post(route,json=payload);self.assertEqual(200,response.status_code);self.assertEqual(2,response.json()['count'])
        self.assertEqual(409,self.client.post(route,json={**payload,'items':payload['items'][:1]}).status_code)
        with self.admin.cursor() as cur:
            cur.execute('SELECT transaction_id,source_review_id,suggestion_method FROM finance.finance_review_events WHERE transaction_id IN (%s,%s,%s)',tuple(t['id'] for t in targets))
            events=cur.fetchall();self.assertEqual(2,len(events))
            self.assertEqual({t['id'] for t in targets[:2]},{str(e[0]) for e in events})
            self.assertTrue(all(str(e[1])==proposal['seed_review_id'] and e[2]=='local-merchant-v2' for e in events))
        # A categorized target invalidates the entire new selection, including an untouched target.
        mixed={**payload,'key':str(uuid.uuid4()),'items':[payload['items'][0],{'id':targets[2]['id'],'previous':None}]}
        self.assertEqual(409,self.client.post(route,json=mixed).status_code)
        remaining=self.client.get('/api/v1/finance/transactions/'+seed['id']+'/suggestions').json()
        self.assertEqual([targets[2]['id']],[t['id'] for t in remaining['transactions']])


    def test_18_classification_taxonomy_merchants_and_meaning(self):
        from fastapi.testclient import TestClient
        names=('SHELL STATION 1234 SYNTHETIC','SHELL STATION 9876 SYNTHETIC','Synthetic transfer','Synthetic unknown')
        for name in names:
            self.import_file(sample(description=name,amount='500.00').replace(b'2026-09-01',b'2018-01-01'))
        data=self.client.get('/api/v1/finance/data?year=2018').json()
        self.assertEqual(9,len(data['transaction_types']))
        roots=[c for c in data['categories'] if c['parent_id'] is None]
        self.assertEqual(18,len(roots));self.assertGreater(len(data['categories']),110)
        rows={r['description']:r for r in data['transactions']}
        seed=rows[names[0]];target=rows[names[1]];transfer=rows[names[2]]
        self.assertEqual('UNKNOWN',seed['transaction_type']);self.assertEqual('Shell',seed['merchant_suggestion'])
        route='/api/v1/finance/transactions/'+seed['id']+'/classification'
        payload={'transaction_type':'EXPENSE','category':'vervoer','subcategory':'vervoer_brandstof',
                 'merchant':'  Shell  ','previous':None,'key':str(uuid.uuid4())}
        self.assertEqual(401,TestClient(self.client.app).post(route,json=payload,headers={'Origin':'http://testserver'}).status_code)
        self.assertEqual(403,self.client.post(route,json=payload,headers={'Origin':'http://other.invalid'}).status_code)
        for invalid in ({'subcategory':'boodschappen_supermarkt'},{'category':'vervoer_brandstof'},
                        {'transaction_type':'BOGUS'},{'merchant':'x'*121},{'merchant':'bad\nname'}):
            self.assertEqual(422,self.client.post(route,json={**payload,**invalid}).status_code)
        with self.admin.cursor() as cur:
            cur.execute('SELECT private_data FROM finance.finance_transactions WHERE id=%s',(seed['id'],));raw=cur.fetchone()[0]
        for _ in range(2):self.assertEqual(200,self.client.post(route,json=payload).status_code)
        self.assertEqual(409,self.client.post(route,json={**payload,'transaction_type':'TRANSFER'}).status_code)
        self.assertEqual(409,self.client.post(route,json={**payload,'key':str(uuid.uuid4())}).status_code)
        proposal=self.client.get('/api/v1/finance/transactions/'+seed['id']+'/suggestions').json()
        self.assertEqual('merchant_marker',proposal['reason'])
        self.assertEqual([target['id']],[r['id'] for r in proposal['transactions']])
        self.assertEqual('vervoer_brandstof',proposal['classification']['subcategory_code'])
        self.assertEqual('Shell',proposal['classification']['merchant'])
        accept={'seed_transaction_id':seed['id'],'seed_review_id':proposal['seed_review_id'],
                'items':[{'id':target['id'],'previous':None}],'key':str(uuid.uuid4())}
        self.assertEqual(200,self.client.post('/api/v1/finance/suggestions/approve',json=accept).status_code)
        self.assertEqual(200,self.client.post('/api/v1/finance/transactions/'+transfer['id']+'/classification',json={
            'transaction_type':'TRANSFER','category':'overboekingen','subcategory':'overboekingen_eigen_rekening',
            'merchant':'','previous':None,'key':str(uuid.uuid4())}).status_code)
        data=self.client.get('/api/v1/finance/data?year=2018').json()
        self.assertEqual('1000.00',data['totals']['expenses']);self.assertEqual('500.00',data['totals']['transfer_out'])
        self.assertEqual('-2000.00',data['totals']['debits']);self.assertEqual('1',data['totals']['unknown_type'])
        filtered=self.client.get('/api/v1/finance/data?year=2018&transaction_type=EXPENSE&subcategory=vervoer_brandstof').json()
        self.assertEqual('2',filtered['totals']['total'])
        approved=next(r for r in data['transactions'] if r['id']==target['id'])
        self.assertEqual('MERCHANT',approved['classification_source']);self.assertTrue(approved['confirmed'])
        self.assertIsNone(approved['confidence']);self.assertEqual('Shell',approved['merchant'])
        with self.admin.cursor() as cur:
            cur.execute('SELECT private_data FROM finance.finance_transactions WHERE id=%s',(seed['id'],));self.assertEqual(raw,cur.fetchone()[0])
            cur.execute('SELECT private_data FROM finance.finance_counterparties WHERE id=%s',(approved['merchant_id'],));self.assertNotIn('Shell',cur.fetchone()[0])
        history=self.client.get('/api/v1/finance/transactions/'+seed['id']+'/classifications').json()['events']
        self.assertEqual(1,len(history));self.assertEqual('MANUAL',history[0]['classification_source'])
        self.assertNotIn('payload_digest',history[0])

    def test_19_manual_priority_unknown_and_conflicting_examples(self):
        from core.finance.store import connection
        import psycopg2
        rows=self.client.get('/api/v1/finance/data?year=2018').json()['transactions']
        seed=next(r for r in rows if r['description'].startswith('SHELL STATION 1234'))
        route='/api/v1/finance/transactions/'+seed['id']+'/classification'
        # A future classifier proposal remains audit-only and cannot displace a manual classification.
        with connection() as conn,conn.cursor() as cur:
            cur.execute("""INSERT INTO finance.finance_review_events(transaction_id,category_code,transaction_type,
                classification_source,confidence,confirmed,supersedes_event_id,actor,idempotency_key,payload_digest,model_version)
                VALUES (%s,'overig','UNKNOWN','AI',0.97,false,%s,'synthetic-classifier',%s,'synthetic','future-test') RETURNING id""",
                (seed['id'],seed['review_id'],str(uuid.uuid4())))
            pending=cur.fetchone()['id']
        current=next(r for r in self.client.get('/api/v1/finance/data?year=2018').json()['transactions'] if r['id']==seed['id'])
        self.assertEqual(seed['review_id'],current['review_id']);self.assertEqual('EXPENSE',current['transaction_type'])
        with self.assertRaises(psycopg2.Error):
            with connection() as conn,conn.cursor() as cur:
                cur.execute("""INSERT INTO finance.finance_review_events(transaction_id,category_code,transaction_type,
                    classification_source,confirmed,supersedes_event_id,actor,idempotency_key,payload_digest)
                    VALUES (%s,'overig','UNKNOWN','RULE',true,%s,'synthetic',%s,'synthetic')""",
                    (seed['id'],str(pending),str(uuid.uuid4())))
        corrected={'transaction_type':'CORRECTION','category':'vervoer','subcategory':'vervoer_brandstof',
                   'merchant':'Shell','previous':seed['review_id'],'key':str(uuid.uuid4())}
        self.assertEqual(200,self.client.post(route,json=corrected).status_code)
        history=self.client.get('/api/v1/finance/transactions/'+seed['id']+'/classifications').json()['events']
        self.assertEqual(3,len(history));self.assertEqual(str(pending),history[0]['supersedes_event_id'])
        self.assertEqual('MANUAL',history[0]['classification_source'])
        # A manual UNKNOWN is a deliberate review, not permission for automatic rewriting.
        unknown=next(r for r in rows if r['description']=='Synthetic unknown')
        self.assertEqual(200,self.client.post('/api/v1/finance/transactions/'+unknown['id']+'/classification',json={
            'transaction_type':'UNKNOWN','category':None,'subcategory':None,'merchant':'','previous':None,'key':str(uuid.uuid4())}).status_code)
        # Two manual examples for the same recognized merchant disagree on accounting meaning.
        target=next(r for r in rows if r['description'].startswith('SHELL STATION 9876'))
        self.assertEqual(200,self.client.post('/api/v1/finance/transactions/'+target['id']+'/classification',json={
            **corrected,'transaction_type':'EXPENSE','previous':target['review_id'],'key':str(uuid.uuid4())}).status_code)
        proposal=self.client.get('/api/v1/finance/transactions/'+seed['id']+'/suggestions').json()
        self.assertEqual('conflicting_examples',proposal['reason']);self.assertEqual(0,proposal['total'])
        # A historical category-only review remains UNKNOWN, without inventing a type.
        legacy_source=sample(description='Legacy category only').replace(b'2026-09-01',b'2017-01-01')
        self.import_file(legacy_source)
        legacy=self.client.get('/api/v1/finance/data?year=2017').json()['transactions'][0]
        with connection() as conn,conn.cursor() as cur:
            cur.execute("""INSERT INTO finance.finance_review_events(transaction_id,category_code,actor,idempotency_key,payload_digest)
                VALUES (%s,'vervoer','owner',%s,'legacy-synthetic')""",(legacy['id'],str(uuid.uuid4())))
        legacy=self.client.get('/api/v1/finance/data?year=2017').json()['transactions'][0]
        self.assertEqual('UNKNOWN',legacy['transaction_type']);self.assertEqual('vervoer',legacy['category_code'])
        from core.finance.classification import conflicts
        self.assertFalse(conflicts({**legacy,'legacy_classification':True},{**legacy,'transaction_type':'EXPENSE'}))
        self.assertTrue(conflicts({**legacy,'legacy_classification':False},{**legacy,'transaction_type':'EXPENSE'}))


    def test_20_taxonomy_constraints_audit_and_safe_rollback(self):
        import psycopg2
        with self.admin.cursor() as cur:
            cur.execute("SELECT id FROM finance.finance_categories WHERE code='vervoer'");parent=cur.fetchone()[0]
            cur.execute("UPDATE finance.finance_categories SET name='Transport',sort_order=99 WHERE code='vervoer'")
            cur.execute('SELECT count(*) FROM finance.finance_category_events WHERE category_id=%s',(parent,));self.assertEqual(1,cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM finance.v_transactions WHERE category_code='vervoer'");self.assertGreater(cur.fetchone()[0],0)
        for statement in (
            "UPDATE finance.finance_categories SET parent_id=id WHERE code='vervoer'",
            "UPDATE finance.finance_categories SET code='new-code' WHERE code='vervoer'",
            "DELETE FROM finance.finance_categories WHERE code='vervoer'",
            "UPDATE finance.finance_categories SET parent_id=(SELECT id FROM finance.finance_categories WHERE code='vervoer_brandstof') WHERE code='wonen'",
            "DELETE FROM finance.finance_category_events"):
            with self.assertRaises(psycopg2.Error):
                with self.admin.cursor() as cur:cur.execute(statement)
        with self.admin.cursor() as cur:cur.execute("UPDATE finance.finance_categories SET active=false WHERE code='vervoer_brandstof'")
        row=next(r for r in self.client.get('/api/v1/finance/data?year=2018').json()['transactions'] if r['description'].startswith('SHELL STATION 1234'))
        self.assertEqual('vervoer_brandstof',row['subcategory_code'])
        invalid={'transaction_type':'EXPENSE','category':'vervoer','subcategory':'vervoer_brandstof',
                 'merchant':'Shell','previous':row['review_id'],'key':str(uuid.uuid4())}
        self.assertEqual(422,self.client.post('/api/v1/finance/transactions/'+row['id']+'/classification',json=invalid).status_code)
        with self.assertRaises(psycopg2.Error):
            with self.admin.cursor() as cur:cur.execute(Path('database/migrations/rollback/20260918_add_finance_classification.sql').read_text(encoding='utf-8'))
        with self.admin.cursor() as cur:cur.execute('ROLLBACK')
        self.assertEqual(200,self.client.get('/api/v1/finance/data?year=2018').status_code)


    def test_21_group_creation_rename_privacy_and_access(self):
        from fastapi.testclient import TestClient
        initial=self.client.get('/api/v1/finance/account-management')
        self.assertEqual(200,initial.status_code);self.assertEqual('no-store',initial.headers['cache-control'])
        self.assertEqual([],initial.json()['groups'])
        self.assertTrue(all(a['group_id'] is None and a['relationship']=='UNASSIGNED' for a in initial.json()['accounts']))
        anonymous=TestClient(self.client.app)
        self.assertEqual(401,anonymous.get('/api/v1/finance/account-management').status_code)
        route='/api/v1/finance/wealth-groups';payload={'name':'Synthetic private','key':str(uuid.uuid4())}
        self.assertEqual(401,anonymous.post(route,json=payload,headers={'Origin':'http://testserver'}).status_code)
        self.assertEqual(403,self.client.post(route,json=payload,headers={'Origin':'http://other.invalid'}).status_code)
        for name in ('', 'x'*81, 'bad\nname', None):
            self.assertEqual(422,self.client.post(route,json={**payload,'name':name}).status_code)
        result=self.client.post(route,json=payload);self.assertEqual(200,result.status_code)
        gid=result.json()['group_id'];self.assertEqual(gid,self.client.post(route,json=payload).json()['group_id'])
        self.assertEqual(409,self.client.post(route,json={**payload,'name':'Changed request'}).status_code)
        g=self.client.get('/api/v1/finance/account-management').json()['groups'][0]
        change={'name':'Synthetic private renamed','previous':g['event_id'],'key':str(uuid.uuid4())}
        for _ in range(2):self.assertEqual(200,self.client.post(route+'/'+gid+'/name',json=change).status_code)
        self.assertEqual(409,self.client.post(route+'/'+gid+'/name',json={**change,'key':str(uuid.uuid4())}).status_code)
        with self.admin.cursor() as cur:
            cur.execute('SELECT private_data FROM finance.finance_wealth_group_events WHERE group_id=%s',(gid,))
            names=cur.fetchall();self.assertEqual(2,len(names));self.assertTrue(all('Synthetic' not in n[0] for n in names))

    def test_22_account_management_and_consistent_filters(self):
        # Valid but wholly fabricated IBANs; never use real account data in fixtures.
        def iban(n):
            bban='TEST'+str(n).zfill(10)
            numeric=''.join(str(ord(c)-55) if c.isalpha() else c for c in bban+'NL00')
            return 'NL'+str(98-int(numeric)%97).zfill(2)+bban
        ibans=[iban(i) for i in range(1,6)]
        entries=[(0,'group seed',1),(0,'group candidate',1),(1,'group savings',0),(1,'group self',1),
                 (2,'group joint',1),(3,'group child',1),(4,'group unassigned',1)]
        for index,description,counter in entries:
            xml=sample(description=description,amount='10.00').replace(IBAN.encode(),ibans[index].encode()).replace(b'2026-09-01',b'2016-01-01')
            xml=xml.replace(b'Synthetische winkel',b'Synthetic managed transfer').replace(b'</RltdPties>',
                ('<CdtrAcct><Id><IBAN>'+ibans[counter]+'</IBAN></Id></CdtrAcct></RltdPties>').encode())
            self.import_file(xml)
        rows={r['description']:r for r in self.client.get('/api/v1/finance/data?year=2016').json()['transactions']}
        type(self).group_rows=rows
        private=self.client.get('/api/v1/finance/account-management').json()['groups'][0]['id']
        joint=self.client.post('/api/v1/finance/wealth-groups',json={'name':'Synthetic joint','key':str(uuid.uuid4())}).json()['group_id']
        child=self.client.post('/api/v1/finance/wealth-groups',json={'name':'Synthetic child','key':str(uuid.uuid4())}).json()['group_id']
        type(self).group_ids=(private,joint,child)
        for desc,gid,relation in [('group seed',private,'OWN'),('group savings',private,'OWN'),('group joint',joint,'JOINT'),('group child',child,'MANAGED')]:
            aid=rows[desc]['account_id'];a=next(a for a in self.client.get('/api/v1/finance/account-management').json()['accounts'] if a['id']==aid)
            payload={'group_id':gid,'relationship':relation,'name':'Synthetic '+desc,'previous':a['group_event_id'],
                     'previous_name':a['name_event_id'],'key':str(uuid.uuid4())}
            route='/api/v1/finance/accounts/'+aid+'/management'
            self.assertEqual(422,self.client.post(route,json={**payload,'relationship':'UNASSIGNED'}).status_code)
            self.assertEqual(422,self.client.post(route,json={**payload,'group_id':None}).status_code)
            self.assertEqual(422,self.client.post(route,json={**payload,'group_id':str(uuid.uuid4())}).status_code)
            for _ in range(2):self.assertEqual(200,self.client.post(route,json=payload).status_code)
            self.assertEqual(409,self.client.post(route,json={**payload,'name':'Changed same key'}).status_code)
            with self.admin.cursor() as cur:
                cur.execute('SELECT count(*) FROM finance.finance_account_group_events WHERE account_id=%s',(aid,));self.assertEqual(1,cur.fetchone()[0])
                cur.execute('SELECT private_data FROM finance.finance_account_name_events WHERE account_id=%s',(aid,));self.assertNotIn('Synthetic',cur.fetchone()[0])
        for group,total in [(private,'4'),(joint,'1'),(child,'1'),('unassigned','1')]:
            for sort in ('amount','description'):
                data=self.client.get('/api/v1/finance/data',params={'year':'2016','group':group,'sort':sort}).json()
                self.assertEqual(total,data['totals']['total']);self.assertEqual(-10*int(total),float(data['totals']['debits']))
                self.assertEqual(int(total),len(data['transactions']))
                self.assertTrue(all(a['group_id']==group for a in data['accounts']) if group!='unassigned' else all(a['group_id'] is None for a in data['accounts']))
        incompatible=self.client.get('/api/v1/finance/data',params={'year':'2016','group':private,'account':rows['group child']['account_id']}).json()
        self.assertEqual('0',incompatible['totals']['total']);self.assertEqual([],incompatible['transactions'])
        self.assertEqual(200,self.client.get('/api/v1/finance/data',params={'group':private.upper()}).status_code)
        self.assertEqual(404,self.client.get('/api/v1/finance/data',params={'group':str(uuid.uuid4())}).status_code)
        aid=rows['group seed']['account_id']
        history=self.client.get('/api/v1/finance/accounts/'+aid+'/management-history').json()['events']
        self.assertEqual(1,len(history));self.assertEqual('OWN',history[0]['relationship']);self.assertNotIn('payload_digest',history[0])

    def test_23_stale_name_and_concurrent_membership_edits(self):
        from fastapi.testclient import TestClient
        aid=self.group_rows['group seed']['account_id']
        def current():return next(a for a in self.client.get('/api/v1/finance/account-management').json()['accounts'] if a['id']==aid)
        a=current();route='/api/v1/finance/accounts/'+aid+'/management'
        payload={'name':'New management name','group_id':self.group_ids[1],'relationship':'JOINT',
                 'previous':a['group_event_id'],'previous_name':a['name_event_id'],'key':str(uuid.uuid4())}
        self.assertEqual(200,self.client.post('/api/v1/finance/accounts/'+aid+'/name',json={'name':'Concurrent rename','previous':a['name_event_id'],'key':str(uuid.uuid4())}).status_code)
        self.assertEqual(409,self.client.post(route,json=payload).status_code)
        self.assertEqual(self.group_ids[0],current()['group_id']);self.assertEqual('Concurrent rename',current()['display_name'])
        a=current();payload.update(group_id=self.group_ids[0],relationship='OWN',previous_name=a['name_event_id'])
        def submit(i):
            c=TestClient(self.client.app);c.cookies.update(self.client.cookies)
            return c.post(route,json={**payload,'name':'Concurrent '+str(i),'key':str(uuid.uuid4())},headers={'Origin':'http://testserver'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,[1,2]))
        self.assertEqual([200,409],sorted(results));self.assertEqual(self.group_ids[0],current()['group_id'])

    def test_24_transfer_boundary_rechecked_without_rewriting_history(self):
        rows=self.group_rows;seed=rows['group seed'];target=rows['group candidate'];savings=rows['group savings']
        self.assertEqual(200,self.client.post('/api/v1/finance/transactions/'+seed['id']+'/classification',json={
            'transaction_type':'TRANSFER','category':'overboekingen','subcategory':'overboekingen_eigen_rekening','merchant':'',
            'previous':None,'key':str(uuid.uuid4())}).status_code)
        route='/api/v1/finance/transactions/'+seed['id']+'/suggestions'
        proposal=self.client.get(route).json();self.assertEqual([target['id']],[r['id'] for r in proposal['transactions']])
        payload={'seed_transaction_id':seed['id'],'seed_review_id':proposal['seed_review_id'],
                 'items':[{'id':target['id'],'previous':None}],'key':str(uuid.uuid4())}
        def move(gid,relation):
            a=next(a for a in self.client.get('/api/v1/finance/account-management').json()['accounts'] if a['id']==savings['account_id'])
            return self.client.post('/api/v1/finance/accounts/'+a['id']+'/management',json={'name':a['display_name'] or '',
                'group_id':gid,'relationship':relation,'previous':a['group_event_id'],'previous_name':a['name_event_id'],'key':str(uuid.uuid4())})
        self.assertEqual(200,move(self.group_ids[1],'JOINT').status_code)
        self.assertEqual('transfer_group_required',self.client.get(route).json()['reason'])
        self.assertEqual(409,self.client.post('/api/v1/finance/suggestions/approve',json=payload).status_code)
        current=next(r for r in self.client.get('/api/v1/finance/data?year=2016').json()['transactions'] if r['id']==seed['id'])
        self.assertEqual(proposal['seed_review_id'],current['review_id']);self.assertEqual('TRANSFER',current['transaction_type'])
        self.assertEqual(200,move(None,'UNASSIGNED').status_code)
        self.assertEqual(0,self.client.get(route).json()['total'])
        self.assertEqual(200,move(self.group_ids[0],'OWN').status_code)
        self.assertEqual(200,self.client.post('/api/v1/finance/suggestions/approve',json=payload).status_code)
        totals=self.client.get('/api/v1/finance/data',params={'group':self.group_ids[0],'year':'2016','category':'overboekingen','transaction_type':'TRANSFER'}).json()['totals']
        self.assertEqual('2',totals['total']);self.assertEqual('20.00',totals['transfer_out']);self.assertEqual('0',totals['expenses'])

    def test_25_membership_constraints_append_only_and_rollback(self):
        from core.finance.store import connection
        import psycopg2
        a,b=self.group_rows['group seed']['account_id'],self.group_rows['group savings']['account_id']
        with self.admin.cursor() as cur:
            cur.execute('SELECT id FROM finance.finance_account_group_events WHERE account_id=%s ORDER BY sequence_no DESC LIMIT 1',(a,));wrong_previous=cur.fetchone()[0]
        with self.assertRaises(psycopg2.Error):
            with connection() as conn,conn.cursor() as cur:
                cur.execute("""INSERT INTO finance.finance_account_group_events(account_id,relationship,supersedes_event_id,actor,idempotency_key,payload_digest)
                    VALUES (%s,'UNASSIGNED',%s,'test',%s,'test')""",(b,wrong_previous,str(uuid.uuid4())))
        for table in ('finance_wealth_groups','finance_wealth_group_events','finance_account_group_events'):
            for sql in ('DELETE FROM finance.'+table,'TRUNCATE finance.'+table):
                with self.assertRaises(psycopg2.Error):
                    with self.admin.cursor() as cur:cur.execute(sql)
        with self.assertRaises(psycopg2.Error):
            with self.admin.cursor() as cur:cur.execute(Path('database/migrations/rollback/20260923_add_finance_wealth_groups.sql').read_text(encoding='utf-8'))
        with self.admin.cursor() as cur:cur.execute('ROLLBACK')
        self.assertEqual(200,self.client.get('/api/v1/finance/account-management').status_code)


    def test_26_bank_balances_backfill_replay_scope_and_rollback(self):
        from tests.test_finance_balances import with_balances
        from core.finance.balances import backfill_one
        from core.finance.store import connection
        import psycopg2
        source=with_balances(sample(message='balance-legacy',description='BALANCE SYNTHETIC',amount='12.34'))
        # Simulate an import made before balance extraction existed.
        with patch('core.finance.balances.persist'):
            self.import_file(source,'balance-legacy.xml')
        with self.admin.cursor() as cur:
            cur.execute("SELECT id FROM finance.finance_accounts WHERE identity_key=%s",(__import__('core.finance.crypto',fromlist=['fingerprint']).fingerprint('account-v1',IBAN),))
            aid=str(cur.fetchone()[0])
            cur.execute('SELECT count(*) FROM finance.finance_transactions');before=cur.fetchone()[0]
        self.assertEqual(1,self.client.get('/api/v1/finance/data').json()['bank_balances']['pending'])
        with connection(worker=True) as conn:self.assertTrue(backfill_one(conn))
        with connection(worker=True) as conn:self.assertFalse(backfill_one(conn))
        data=self.client.get('/api/v1/finance/data',params={'account':aid}).json()['bank_balances']
        self.assertEqual('7.66',data['total']);self.assertEqual('2026-09-01',data['as_of'])
        self.assertEqual('20.00',data['accounts'][0]['opening'])
        self.assertEqual(data,self.client.get('/api/v1/finance/data',params={'account':aid,'category':'uncategorized','transaction_type':'INCOME'}).json()['bank_balances'])
        historic=self.client.get('/api/v1/finance/data',params={'account':aid,'date_from':'2026-01-01','date_to':'2026-08-30'}).json()['bank_balances']
        self.assertIsNone(historic['total'])
        self.assertTrue(self.import_file(source,'balance-copy.xml')['replay'])
        with self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM finance.finance_transactions');self.assertEqual(before,cur.fetchone()[0])
            cur.execute('SELECT private_data,batch_id FROM finance.finance_bank_balances')
            rows=cur.fetchall();self.assertEqual(1,len(rows));self.assertNotIn('7.66',rows[0][0]);batch=str(rows[0][1])
        for table in ('finance_bank_balances','finance_balance_extractions'):
            for verb in ('DELETE FROM','TRUNCATE'):
                with self.assertRaises(psycopg2.Error):
                    with self.admin.cursor() as cur:cur.execute(verb+' finance.'+table)
        with self.assertRaises(psycopg2.Error):
            with self.admin.cursor() as cur:cur.execute(Path('database/migrations/rollback/20260923_add_finance_bank_balances.sql').read_text())
        with self.admin.cursor() as cur:cur.execute('ROLLBACK')
        self.assertEqual(200,self.client.post('/api/v1/finance/imports/'+batch+'/rollback',json={'confirm':True}).status_code)
        self.assertIsNone(self.client.get('/api/v1/finance/data',params={'account':aid}).json()['bank_balances']['total'])

    def test_27_balance_snapshot_conflicts_and_refresh_authorization(self):
        from tests.test_finance_balances import with_balances
        from core.finance.crypto import fingerprint
        from core.finance.store import connection
        from fastapi.testclient import TestClient
        with self.admin.cursor() as cur:
            cur.execute('SELECT id FROM finance.finance_accounts WHERE identity_key=%s',(fingerprint('account-v1',IBAN),));aid=str(cur.fetchone()[0])
        self.import_file(with_balances(sample(message='bank-a',description='BANK A')))
        self.import_file(with_balances(sample(message='bank-b',description='BANK B'),opening='30.00',closing='17.66'))
        data=self.client.get('/api/v1/finance/data',params={'account':aid}).json()['bank_balances']
        self.assertIsNone(data['total']);self.assertEqual('conflict',data['accounts'][0]['status'])
        outsider=TestClient(self.client.app);outsider.headers['origin']='http://testserver'
        self.assertEqual(401,outsider.post('/api/v1/finance/balances/refresh',json={}).status_code)
        self.assertEqual(403,self.client.post('/api/v1/finance/balances/refresh',json={},headers={'origin':'http://other'}).status_code)
        response=self.client.post('/api/v1/finance/balances/refresh',json={});self.assertEqual(200,response.status_code)
        self.assertEqual(response.json(),self.client.post('/api/v1/finance/balances/refresh',json={}).json())


    def test_28_asn_number_is_primary_duplicate_key(self):
        from tests.test_finance_bank_references import numbered,account
        from core.finance.crypto import fingerprint
        source=numbered(description='NUMBERED SYNTHETIC')
        first=self.import_file(source)
        self.assertEqual('imported',first['status'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda i:self.import_file(numbered(message='download-'+str(i),description='NUMBERED SYNTHETIC')),range(2)))
        self.assertTrue(all(r['unresolved']==0 for r in results))
        self.assertTrue(self.import_file(source)['replay'])
        # Same amount/date/text, DIFFERENT bank number really is a second payment.
        self.assertEqual(0,self.import_file(numbered(ref='SYNTHETIC-002',description='NUMBERED SYNTHETIC'))['unresolved'])
        # Same number on another account must not collapse across accounts.
        self.assertEqual(0,self.import_file(numbered(n=2,description='NUMBERED SYNTHETIC'))['unresolved'])
        with self.admin.cursor() as cur:
            cur.execute('SELECT id FROM finance.finance_accounts WHERE identity_key=%s',(fingerprint('account-v1',account()),));aid=str(cur.fetchone()[0])
            cur.execute('SELECT count(*) FROM finance.finance_transactions WHERE account_id=%s',(aid,));self.assertEqual(2,cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM finance.finance_duplicate_events WHERE actor='asn-ntryref-v1' AND decision='same'");self.assertEqual(2,cur.fetchone()[0])
            cur.execute('SELECT private_data FROM finance.finance_record_bank_references');self.assertTrue(all('SYNTHETIC' not in r[0] for r in cur.fetchall()))
        data=self.client.get('/api/v1/finance/data',params={'account':aid}).json()
        self.assertEqual('2',data['totals']['total'])

    def test_29_conflicting_ids_stay_visible_with_original_payment(self):
        from tests.test_finance_bank_references import numbered
        result=self.import_file(numbered(message='conflicting-download',description='NUMBERED SYNTHETIC',amount='99.99'))
        self.assertEqual(1,result['unresolved'])
        pending=self.client.get('/api/v1/finance/unresolved');self.assertEqual(200,pending.status_code)
        row=next(r for r in pending.json()['records'] if r.get('entry_reference')=='SYNTHETIC-001')
        self.assertEqual('NUMBERED SYNTHETIC',row['candidates'][0]['description'])
        self.assertEqual('-12.34',row['candidates'][0]['amount'])
        self.assertEqual('SYNTHETIC-001',row['candidates'][0]['entry_reference'])
        self.assertFalse(row['candidates'][0]['can_link'])
        self.assertNotIn('private_data',row['candidates'][0])
        self.assertNotIn('identity_key',row['candidates'][0])
        result=self.import_file(numbered(message='conflict-again',description='NUMBERED SYNTHETIC'))
        self.assertEqual(1,result['unresolved']) # Historical conflict is not silently ignored.

    def test_30_historical_reconciliation_without_reimport_and_resource_gate(self):
        from dataclasses import asdict
        from unittest.mock import MagicMock
        from tests.test_finance_bank_references import numbered,account
        from core.finance.store import connection
        from core.finance.crypto import fingerprint
        import finance_worker
        # Simulate the previous importer: no indexed references or reference in payload.
        with patch('core.finance.bank_references.usable',return_value=False),patch('core.finance.bank_references.mark_extracted'),patch('core.finance.store.asdict',side_effect=lambda e:{k:v for k,v in asdict(e).items() if k!='entry_reference'}):
            self.import_file(numbered(ref='OLD-001',n=3,description='HISTORICAL SYNTHETIC'))
            overlap=self.import_file(numbered(ref='OLD-001',n=3,description='HISTORICAL SYNTHETIC',message='overlap'))
            distinct=self.import_file(numbered(ref='OLD-002',n=3,description='HISTORICAL SYNTHETIC',message='second-real-payment'))
        self.assertEqual(1,overlap['unresolved']);self.assertEqual(1,distinct['unresolved'])
        with self.admin.cursor() as cur:
            cur.execute('SELECT id FROM finance.finance_accounts WHERE identity_key=%s',(fingerprint('account-v1',account(3)),));aid=str(cur.fetchone()[0])
            cur.execute('SELECT count(*) FROM finance.finance_import_batches');batches=cur.fetchone()[0]
            cur.execute('SELECT count(*) FROM finance.finance_source_documents');sources=cur.fetchone()[0]
            # Finish the unrelated synthetic balance request from test 27.
            cur.execute("UPDATE finance.finance_ingest_jobs SET status='done' WHERE status IN ('pending','running')")
        response=self.client.post('/api/v1/finance/duplicates/reconcile',json={});self.assertEqual(200,response.status_code)
        jid=response.json()['job_id']
        self.assertEqual(jid,self.client.post('/api/v1/finance/duplicates/reconcile',json={}).json()['job_id'])
        with patch('finance_worker.gate',return_value='controlled_execution_priority'),patch('finance_worker.source_root',side_effect=AssertionError('No filesystem import allowed')):
            finance_worker.scan(MagicMock())
        with self.admin.cursor() as cur:
            cur.execute('SELECT status,waiting_reason FROM finance.finance_ingest_jobs WHERE id=%s',(jid,));self.assertEqual(('pending','controlled_execution_priority'),cur.fetchone())
            cur.execute('SELECT count(*) FROM finance.finance_transactions WHERE account_id=%s',(aid,));self.assertEqual(1,cur.fetchone()[0])
        with patch('finance_worker.gate',return_value=None),patch('finance_worker.source_root',side_effect=AssertionError('No filesystem import allowed')):
            finance_worker.scan(MagicMock())
        with self.admin.cursor() as cur:
            cur.execute('SELECT status,error_code FROM finance.finance_ingest_jobs WHERE id=%s',(jid,));self.assertEqual(('done',None),cur.fetchone())
            cur.execute('SELECT count(*) FROM finance.finance_transactions WHERE account_id=%s',(aid,));self.assertEqual(2,cur.fetchone()[0])
            cur.execute('SELECT count(*) FROM finance.finance_import_batches');self.assertEqual(batches,cur.fetchone()[0])
            cur.execute('SELECT count(*) FROM finance.finance_source_documents');self.assertEqual(sources,cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM finance.finance_import_records r WHERE r.account_id=%s AND r.initial_outcome='unresolved' AND NOT EXISTS(SELECT 1 FROM finance.finance_duplicate_events d WHERE d.record_id=r.id)",(aid,));self.assertEqual(0,cur.fetchone()[0])
            cur.execute('SELECT count(*) FROM finance.finance_duplicate_events');decisions=cur.fetchone()[0]
        # Re-run remains idempotent, including still unresolved conflicts elsewhere.
        self.client.post('/api/v1/finance/duplicates/reconcile',json={})
        with patch('finance_worker.gate',return_value=None),patch('finance_worker.source_root',side_effect=AssertionError('No filesystem import allowed')):
            finance_worker.scan(MagicMock())
        with self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM finance.finance_duplicate_events');self.assertEqual(decisions,cur.fetchone()[0])

    def test_31_reference_evidence_auth_constraints_and_rollback(self):
        import psycopg2
        from fastapi.testclient import TestClient
        from core.finance.store import connection
        outsider=TestClient(self.client.app);outsider.headers['origin']='http://testserver'
        self.assertEqual(401,outsider.post('/api/v1/finance/duplicates/reconcile',json={}).status_code)
        self.assertEqual(403,self.client.post('/api/v1/finance/duplicates/reconcile',json={},headers={'origin':'http://other'}).status_code)
        for table in ('finance_record_bank_references','finance_reference_extractions'):
            for sql in ('DELETE FROM finance.'+table,'TRUNCATE finance.'+table):
                with self.assertRaises(psycopg2.Error):
                    with self.admin.cursor() as cur:cur.execute(sql)
        with self.assertRaises(psycopg2.Error):
            with self.admin.cursor() as cur:cur.execute(Path('database/migrations/rollback/20260924_add_finance_bank_references.sql').read_text())
        with self.admin.cursor() as cur:cur.execute('ROLLBACK')
        self.assertEqual(200,self.client.get('/api/v1/finance/data').status_code)


    def test_32_manual_distinct_decisions_are_never_rewritten(self):
        from tests.test_finance_bank_references import numbered,account
        from core.finance.crypto import fingerprint
        from core.finance.store import connection
        from core.finance.bank_references import backfill_one,reconcile_chunk
        with patch('core.finance.bank_references.usable',return_value=False),patch('core.finance.bank_references.mark_extracted'):
            self.import_file(numbered(ref='MANUAL-001',n=4,description='MANUAL SYNTHETIC'))
            self.import_file(numbered(ref='MANUAL-001',n=4,description='MANUAL SYNTHETIC',message='second'))
        with self.admin.cursor() as cur:
            cur.execute('SELECT id FROM finance.finance_accounts WHERE identity_key=%s',(fingerprint('account-v1',account(4)),));aid=str(cur.fetchone()[0])
            cur.execute("SELECT id FROM finance.finance_import_records WHERE account_id=%s AND initial_outcome='unresolved'",(aid,));rid=str(cur.fetchone()[0])
        response=self.client.post('/api/v1/finance/unresolved/'+rid,json={'key':str(uuid.uuid4()),'decision':'distinct'})
        self.assertEqual(200,response.status_code)
        while True:
            with connection(worker=True) as conn:more=backfill_one(conn)
            if not more:break
        incoming=self.import_file(numbered(ref='MANUAL-001',n=4,description='MANUAL SYNTHETIC',message='third'))
        self.assertEqual(1,incoming['unresolved'])
        after=None
        while True:
            with connection(worker=True) as conn:after=reconcile_chunk(conn,after,limit=1)
            if after is None:break
        with self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM finance.finance_transactions WHERE account_id=%s',(aid,));self.assertEqual(2,cur.fetchone()[0])
            cur.execute('SELECT actor,decision FROM finance.finance_duplicate_events WHERE record_id=%s',(rid,));self.assertEqual(('owner','distinct'),cur.fetchone())

    def test_33_rolled_back_evidence_can_link_again_without_duplicate_booking(self):
        from tests.test_finance_bank_references import numbered,account
        from core.finance.crypto import fingerprint
        self.import_file(numbered(ref='ROLLBACK-001',n=5,description='ROLLBACK SYNTHETIC'))
        with self.admin.cursor() as cur:
            cur.execute('SELECT id FROM finance.finance_accounts WHERE identity_key=%s',(fingerprint('account-v1',account(5)),));aid=str(cur.fetchone()[0])
            cur.execute('SELECT batch_id FROM finance.finance_import_records WHERE account_id=%s',(aid,));batch=str(cur.fetchone()[0])
        self.assertEqual(200,self.client.post('/api/v1/finance/imports/'+batch+'/rollback',json={'confirm':True}).status_code)
        self.assertEqual('0',self.client.get('/api/v1/finance/data',params={'account':aid}).json()['totals']['total'])
        self.assertEqual(0,self.import_file(numbered(ref='ROLLBACK-001',n=5,description='ROLLBACK SYNTHETIC',message='another-source'))['unresolved'])
        self.assertEqual('1',self.client.get('/api/v1/finance/data',params={'account':aid}).json()['totals']['total'])
        with self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM finance.finance_transactions WHERE account_id=%s',(aid,));self.assertEqual(1,cur.fetchone()[0])


if __name__=='__main__': unittest.main()
