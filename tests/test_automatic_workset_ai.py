import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from core.semantic.automatic_workset_ai import eligible, enqueue_page, REQUESTED_BY


class AutomaticWorksetAiTests(unittest.TestCase):
    def row(self, **changes):
        return dict(file_id=42, filename='xyz.pdf', path='/volume1/data/Persoonlijk/Actief/Te beoordelen/xyz.pdf',
                    content_sha256='a'*64, workset_status='active', **changes)

    def test_unknown_active_document_qualifies(self):
        self.assertTrue(eligible(self.row()))

    def test_known_category_or_human_review_or_redundant_does_not(self):
        for values in ({'category':'finance'}, {'review_decision':'accepted'},
                       {'review_decision':'needs_review'}, {'review_decision':'passed'},
                       {'redundant_file_id':True}, {'corrected_lifecycle':'archive'}):
            self.assertFalse(eligible(self.row(**values)), values)

    def test_human_active_override_and_expiry(self):
        row = self.row(corrected_lifecycle='active')
        row['workset_status'] = 'inactive'
        self.assertTrue(eligible(row))
        row['lifecycle_active_until'] = datetime.now(timezone.utc)-timedelta(seconds=1)
        self.assertFalse(eligible(row))
        row['corrected_lifecycle'] = None
        self.assertFalse(eligible(row))

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
            cur.fetchone.side_effect=[{'count':0},{'id':'job'}]
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
        cur.fetchone.side_effect=[{'count':19},{'id':'job'}]
        cur.fetchall.return_value=[self.row(),{**self.row(),'file_id':43}]
        self.assertEqual((42,1),enqueue_page(cur,0,'model','prompt'))
