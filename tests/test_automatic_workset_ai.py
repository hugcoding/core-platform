import unittest
from unittest.mock import MagicMock, patch
from core.semantic.automatic_workset_ai import eligible, enqueue_page, REQUESTED_BY


class AutomaticWorksetAiTests(unittest.TestCase):
    def test_discovery_query_filters_before_the_bounded_page(self):
        from core.semantic.automatic_workset_ai import PAGE_SQL
        page = PAGE_SQL.split(")\nSELECT", 1)[0]
        self.assertIn("effective_workset_status='inactive'", page)
        self.assertIn("review_state='pending'", page)
        self.assertIn("review_family='general'", page)

    def row(self, **changes):
        row = dict(file_id=42, filename='xyz.pdf', path='/volume1/data/Persoonlijk/Inactief/Te beoordelen/xyz.pdf',
                   content_sha256='a'*64, workset_status='inactive', effective_workset_status='inactive',
                   review_state='pending', review_family='general')
        row.update(changes)
        return row

    def test_unknown_inactive_general_document_qualifies(self):
        self.assertTrue(eligible(self.row()))

    def test_reviewed_known_active_or_redundant_does_not(self):
        for values in ({'review_family':'tax_documents'}, {'review_state':'reviewed'},
                       {'redundant_file_id':True}, {'effective_workset_status':'active'}):
            self.assertFalse(eligible(self.row(**values)), values)

    def test_core_keyword_proposal_does_not_need_ai(self):
        row = self.row()
        row['filename'] = 'sollicitatie motivatiebrief.pdf'
        self.assertFalse(eligible(row))

    def test_backpressure_skips_discovery(self):
        cur = MagicMock()
        cur.fetchone.return_value = {'count':20}
        self.assertEqual((10,0), enqueue_page(cur,10,'model','prompt'))
        self.assertEqual(1,cur.execute.call_count)

    def test_stable_identity_and_no_repeat_after_any_attempt(self):
        identities=[]
        for _ in range(2):
            cur=MagicMock()
            cur.fetchone.side_effect=[{'count':0},{'count':0},{'id':'job'}]
            cur.fetchall.return_value=[self.row()]
            self.assertEqual((0,1),enqueue_page(cur,0,'model','prompt'))
            sql, params=cur.execute.call_args.args
            self.assertIn('ON CONFLICT DO NOTHING',sql)
            self.assertIn('content_sha256=%s',sql)
            self.assertNotIn("status='pending'",sql)
            self.assertIn(REQUESTED_BY,params)
            identities.append(params[0])
        self.assertEqual(*identities)

    def test_partial_page_resumes_after_last_processed_file(self):
        cur=MagicMock()
        cur.fetchone.side_effect=[{'count':4},{'count':0},{'id':'job'}]
        cur.fetchall.return_value=[self.row(),{**self.row(),'file_id':43}]
        self.assertEqual((42,1),enqueue_page(cur,0,'model','prompt'))

    def test_hourly_limit_stops_discovery(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [{'count': 0}, {'count': 10}]
        self.assertEqual((7, 0), enqueue_page(cur, 7, 'model', 'prompt'))
        self.assertEqual(2, cur.execute.call_count)
