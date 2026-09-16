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
        for query in ('sort=amount;DROP TABLE finance.finance_transactions','direction=desc nulls first'):
            self.assertEqual(422,self.client.get('/api/v1/finance/data',params=dict([query.split('=',1)])).status_code)


if __name__=='__main__': unittest.main()
