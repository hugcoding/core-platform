import importlib
import sys
import types
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]


class DashboardWorksetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class FakeFastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def mount(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda function: function

            def post(self, *args, **kwargs):
                return lambda function: function

        class FakeHTTPException(RuntimeError):
            def __init__(self, status_code, detail):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        fastapi = types.ModuleType("fastapi")
        fastapi.FastAPI = FakeFastAPI
        fastapi.HTTPException = FakeHTTPException
        fastapi.Query = lambda default, **kwargs: default
        fastapi.Body = lambda default, **kwargs: default
        responses = types.ModuleType("fastapi.responses")
        responses.FileResponse = lambda path: path
        responses.RedirectResponse = lambda path, status_code=307: (path, status_code)
        responses.Response = lambda **kwargs: kwargs
        staticfiles = types.ModuleType("fastapi.staticfiles")
        staticfiles.StaticFiles = lambda **kwargs: kwargs
        modules = {
            "psycopg2": mock.MagicMock(), "redis": mock.MagicMock(),
            "fastapi": fastapi, "fastapi.responses": responses,
            "fastapi.staticfiles": staticfiles,
        }
        with mock.patch.dict(sys.modules, modules):
            cls.dashboard = importlib.import_module("dashboard.app")

    def test_smb_path_maps_only_data_share(self):
        self.assertEqual(
            r"\\192.168.68.105\data\import\document.docx",
            self.dashboard.smb_path("/volume1/data/import/document.docx"),
        )
        self.assertEqual("", self.dashboard.smb_path("/volume1/private/document.docx"))

    def test_workset_response_is_read_only_and_exposes_reason(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        row = {
            "file_id": 1, "content_group_id": "group", "filename": "document.docx",
            "extension": "docx", "path": "/volume1/data/import/document.docx",
            "size_bytes": 42, "workset_status": "active",
            "reason_code": "filesystem_mtime_within_configured_window",
            "last_qualifying_activity_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
            "category": None, "document_family": None,
            "latest_review_decision": "accepted",
            "latest_review_family": "interview_preparation",
        }
        with mock.patch.object(self.dashboard, "db_connect", return_value=connection), mock.patch.object(
            self.dashboard, "query_one", side_effect=[
                {"total": 3, "active": 1, "inactive": 1, "needs_review": 1},
                {"available": False},
                {"available": False},
                {"available": False},
            ],
        ), mock.patch.object(self.dashboard, "query_all", return_value=[row]) as query_all:
            result = self.dashboard.workset(
                status="active", extension="docx", search="document", review_state="all",
                limit=50, offset=0,
            )
        self.assertEqual("read_only", result["mode"])
        self.assertEqual(
            {"database_writes": False, "file_mutations": False, "model_updates": False},
            result["safety"],
        )
        self.assertEqual("not_reviewed", result["documents"][0]["classification_status"])
        self.assertEqual("interview_preparation", result["documents"][0]["effective_document_family"])
        self.assertEqual("accepted_portal_review", result["documents"][0]["effective_family_source"])
        self.assertEqual(
            "interview_preparation",
            result["documents"][0]["target_proposal"]["document_family_code"],
        )
        self.assertLessEqual(len(result["documents"][0]["review_options"]["compact_families"]), 5)
        self.assertEqual("document-taxonomy-v1", result["review_taxonomy"]["version"])
        self.assertIn("filesystem_mtime", result["documents"][0]["reason_code"])
        self.assertEqual(r"\\192.168.68.105\data\import\document.docx", result["documents"][0]["smb_path"])
        params = query_all.call_args.args[2]
        self.assertEqual(("active", "docx", "%document%", "%document%"), params)

    def test_source_limits_mutation_to_append_only_review_events(self):
        source = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
        self.assertEqual(5, source.count("@app.post"))
        self.assertIn("INSERT INTO public.document_review_events", source)
        self.assertNotIn("UPDATE public.", source)
        self.assertNotIn("DELETE FROM", source)
        self.assertNotIn("shutil.move", source)
        self.assertIn('"model_updates": False', source)
        self.assertIn("ILIKE %s", source)
        self.assertIn("enriched[offset:offset + limit]", source)
        self.assertIn('@app.get("/api/v1/workset/{file_id}/reviews")', source)
        self.assertIn('@app.get("/api/v1/workset/reviews/export")', source)
        self.assertIn("review_decision", source)
        self.assertIn("proposed_category_label", source)
        self.assertIn("proposed_family_label", source)
        self.assertIn("proposed_target_path", source)
        self.assertIn("privacy_classification", source)
        self.assertIn("propose_privacy", source)
        self.assertIn("document_review_batches", source)
        self.assertIn("privacy_confirmation_included", source)
        self.assertIn('target-path-suggestion")', source)
        self.assertIn('target-path-preview")', source)
        self.assertIn("target_path_suggestion_decision", source)
        self.assertIn("proposal_evidence", source)
        self.assertIn("apply_similar_review_proposals", source)
        self.assertIn('@app.post("/api/v1/workset/ai-runs")', source)
        self.assertIn("%s::uuid[]", source)
        self.assertIn('@app.post("/api/v1/workset/nominations")', source)
        self.assertIn("workset_status_unchanged", source)
        self.assertIn("archive_status_unchanged", source)

    def test_deletion_nomination_is_append_only_and_keeps_workset_active(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        nomination_id = uuid.uuid4()
        cursor.fetchone.return_value = (
            nomination_id, datetime(2026, 8, 15, tzinfo=timezone.utc),
            1, "deletion", "nominated",
        )
        row = {
            "file_id": 1, "content_group_id": uuid.uuid4(), "content_sha256": "e" * 64,
            "filename": "document.pdf", "extension": "pdf",
            "path": "/volume1/data/import/document.pdf", "workset_status": "active",
            "category": "finance", "document_family": "tax_documents", "sensitivity": None,
        }
        policy = {
            "id": uuid.uuid4(), "policy_code": "document_retention",
            "policy_version": "retention-nomination-v1",
            "configuration": {"archive_review_days": 0, "deletion_review_days": 90},
        }
        with mock.patch.dict("os.environ", {
            "CORE_REVIEW_WRITES_ENABLED": "true", "CORE_ENVIRONMENT": "acceptance",
        }), mock.patch.object(self.dashboard, "db_connect", return_value=connection), mock.patch.object(
            self.dashboard, "query_one", return_value={"available": True},
        ), mock.patch.object(
            self.dashboard, "query_all", side_effect=[[row], [], [policy]],
        ):
            result = self.dashboard.create_document_lifecycle_nomination({
                "file_id": 1, "idempotency_key": str(uuid.uuid4()),
                "nomination_type": "deletion", "action": "nominated",
                "reason": "Dubbele tijdelijke export",
            })
        sql = cursor.execute.call_args.args[0]
        self.assertIn("INSERT INTO public.document_lifecycle_nomination_events", sql)
        self.assertNotIn("UPDATE", sql)
        self.assertTrue(result["workset_status_unchanged"])
        self.assertTrue(result["archive_status_unchanged"])
        self.assertFalse(result["file_mutations"])
        self.assertEqual("deletion", result["nomination_type"])

    def test_stored_ai_proposal_keeps_file_identity_for_portal_refresh(self):
        row = {
            "file_id": 42,
            "path": "/volume1/data/import/document.pdf",
            "filename": "document.pdf",
            "extension": "pdf",
            "workset_status": "inactive",
            "ai_proposal_id": uuid.uuid4(),
            "ai_run_id": uuid.uuid4(),
            "ai_status": "abstained",
            "ai_confidence": "low",
            "ai_relation_kind": "none",
            "ai_reason": "insufficient_evidence",
        }
        result = self.dashboard.enrich_workset_row(row)
        self.assertEqual(42, result["ai_proposal"]["file_id"])

    def test_portal_enhancements_follow_explicit_render_event(self):
        workset = (ROOT / "dashboard" / "static" / "workset.js").read_text(encoding="utf-8")
        ai = (ROOT / "dashboard" / "static" / "workset-ai.js").read_text(encoding="utf-8")
        similar = (ROOT / "dashboard" / "static" / "similar-documents.js").read_text(encoding="utf-8")
        trajectory = (ROOT / "dashboard" / "static" / "trajectory-learning.js").read_text(encoding="utf-8")
        self.assertIn("new CustomEvent('workset:rendered')", workset)
        self.assertIn("'workset:rendered',decorateBulkCards", workset)
        self.assertIn("'workset:rendered',updateAiButton", ai)
        self.assertIn("'workset:rendered',renderSimilarDocumentProposals", similar)
        self.assertIn("'workset:rendered',renderTrajectoryLearning", trajectory)
        self.assertIn("source_review_event_ids", trajectory)
        self.assertNotIn("MutationObserver", workset + ai + similar + trajectory)

    def test_context_sort_uses_review_time_for_reviewed_documents(self):
        order = self.dashboard.workset_order_by("context", "reviewed", "all", True)
        self.assertIn("r.created_at DESC NULLS LAST", order)
        self.assertTrue(order.endswith("LOWER(w.filename), w.filename, w.file_id"))

    def test_context_sort_uses_activity_for_open_documents(self):
        order = self.dashboard.workset_order_by("context", "pending", "all", True)
        self.assertIn("w.last_qualifying_activity_at DESC NULLS LAST", order)
        self.assertTrue(order.endswith("LOWER(w.filename), w.filename, w.file_id"))

    def test_explicit_filename_sort_is_deterministic(self):
        ascending = self.dashboard.workset_order_by("filename_asc", "pending", "all", True)
        descending = self.dashboard.workset_order_by("filename_desc", "pending", "all", True)
        self.assertEqual(" ORDER BY LOWER(w.filename), w.filename, w.file_id", ascending)
        self.assertIn("LOWER(w.filename) DESC", descending)
        self.assertTrue(descending.endswith("w.file_id"))

    def test_workset_portal_exposes_sort_control(self):
        html = (ROOT / "dashboard" / "static" / "workset.html").read_text(encoding="utf-8")
        script = (ROOT / "dashboard" / "static" / "workset.js").read_text(encoding="utf-8")
        self.assertIn('id="worksetSort"', html)
        self.assertIn('value="context"', html)
        self.assertIn("sort:ws('worksetSort').value", script)

    def test_overview_uses_current_filtered_review_count(self):
        script = (ROOT / "dashboard" / "static" / "workset.js").read_text(encoding="utf-8")
        self.assertIn("[label,state.filteredTotal,'review','huidige filters']", script)
        self.assertIn("'Lifecycle beoordelen',state.worksetSummary.needs_review", script)
        self.assertIn("review==='pending'?'Te beoordelen'", script)

    def test_deferred_and_not_applicable_reviews_have_distinct_labels(self):
        script = (ROOT / "dashboard" / "static" / "workset.js").read_text(encoding="utf-8")
        self.assertIn("needs_review:'Uitgesteld'", script)
        self.assertIn("passed:'Niet beoordelen'", script)

    def test_ai_lineage_uses_accessible_compact_info_control(self):
        script = (ROOT / "dashboard" / "static" / "workset-ai.js").read_text(encoding="utf-8")
        css = (ROOT / "dashboard" / "static" / "workset.css").read_text(encoding="utf-8")
        self.assertIn('class="ai-info-button"', script)
        self.assertIn('aria-expanded="false"', script)
        self.assertIn('role="tooltip"', script)
        for field in ("confidence", "reason", "privacy_advice", "model_id", "prompt_version", "created_at"):
            self.assertIn(f"proposal.{field}", script)
        self.assertIn(".ai-info:hover .ai-info-popover", css)
        self.assertNotIn("className='ai-proposal'", script)

    def test_similarity_evidence_requires_matching_accepted_source_review(self):
        connection = mock.MagicMock()
        evidence = {
            "status": "consensus_proposal", "score": 1.0,
            "source_review_event_ids": ["aa4aee14-04f1-4e98-9df9-d91123302c83"],
            "related_file_ids": [7], "normalized_identity": "motivatiebrief duo",
        }
        with mock.patch.object(self.dashboard, "query_all", return_value=[{
            "id": evidence["source_review_event_ids"][0], "file_id": 7,
            "corrected_category_code": "work_career",
            "corrected_document_family_code": "motivation_letters",
        }]):
            result = self.dashboard.validated_similarity_evidence(
                connection, evidence, "work_career", "motivation_letters",
            )
        self.assertEqual("normalized_filename_cross_format", result["match_kind"])
        self.assertEqual([7], result["related_file_ids"])

    def test_target_path_suggestion_is_advisory(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        with mock.patch.object(self.dashboard, "db_connect", return_value=connection), mock.patch.object(
            self.dashboard, "query_one", return_value={"filename": "aangifte.pdf"},
        ), mock.patch.object(self.dashboard, "query_all", return_value=[{
            "proposed_target_path": "/volume1/data/Persoonlijk/Actief/Geldzaken/Belasting/vorig.pdf",
            "proposal_target_path": None,
        }]):
            result = self.dashboard.workset_target_path_suggestion(
                1, "/volume1/data/Persoonlijk/Actief/Geldzaken/Belastingen",
            )
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual("advisory_only", result["mode"])
        self.assertFalse(result["file_mutations"])

    def test_workset_ai_rejects_more_than_five_selected_documents(self):
        with mock.patch.dict("os.environ", {
            "CORE_REVIEW_WRITES_ENABLED": "true", "CORE_LLM_ENABLED": "true",
        }):
            with self.assertRaises(self.dashboard.HTTPException) as raised:
                self.dashboard.create_workset_ai_run({
                    "idempotency_key": str(uuid.uuid4()), "file_ids": [1, 2, 3, 4, 5, 6],
                    "filter_snapshot": {"status": "active"},
                })
        self.assertEqual(422, raised.exception.status_code)

    def test_changed_category_and_family_recalculate_read_only_preview(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        row = {
            "file_id": 1, "filename": "aangifte.pdf", "extension": "pdf",
            "path": "/volume1/data/import/aangifte.pdf", "workset_status": "active",
            "lifecycle": None,
        }
        with mock.patch.object(self.dashboard, "db_connect", return_value=connection), mock.patch.object(
            self.dashboard, "query_all", return_value=[row],
        ):
            result = self.dashboard.workset_target_path_preview(1, "finance", "tax_documents")
        self.assertEqual("live_preview", result["mode"])
        self.assertIn("/Geldzaken/Belastingen/aangifte.pdf", result["suggested_target_path"])
        self.assertFalse(result["database_writes"])
        self.assertFalse(result["file_mutations"])

    def test_bulk_preview_contains_only_compact_confirmation_fields(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        row = {
            "file_id": 1, "content_group_id": uuid.uuid4(), "content_sha256": "c" * 64,
            "filename": "aangifte.pdf", "extension": "pdf",
            "path": "/volume1/data/import/aangifte.pdf", "workset_status": "active",
            "lifecycle": None, "sensitivity": None,
        }
        payload = {"items": [{"file_id": 1, "category": "finance",
                               "family": "tax_documents", "privacy": "medium",
                               "manual_target_path": ""}]}
        with mock.patch.object(self.dashboard, "db_connect", return_value=connection), mock.patch.object(
            self.dashboard, "query_all", return_value=[row],
        ):
            result = self.dashboard.preview_bulk_workset_review(payload)
        self.assertEqual("confirmation_required", result["mode"])
        self.assertEqual({"file_id", "filename", "target_path", "privacy"}, set(result["items"][0]))
        self.assertEqual("medium", result["items"][0]["privacy"])
        self.assertFalse(result["database_writes"])

    def test_bulk_preview_rejects_duplicate_file_selection(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        item = {"file_id": 1, "category": "finance", "family": "tax_documents", "privacy": "medium"}
        with mock.patch.object(self.dashboard, "db_connect", return_value=connection):
            with self.assertRaises(self.dashboard.HTTPException) as raised:
                self.dashboard.preview_bulk_workset_review({"items": [item, item]})
        self.assertEqual(422, raised.exception.status_code)

    def test_bulk_apply_writes_batch_and_separate_target_and_privacy_events(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        batch_id = uuid.uuid4()
        cursor.fetchone.return_value = (batch_id, datetime(2026, 8, 14, tzinfo=timezone.utc))
        cursor.fetchall.return_value = []
        row = {
            "file_id": 1, "content_group_id": uuid.uuid4(), "content_sha256": "d" * 64,
            "filename": "aangifte.pdf", "extension": "pdf",
            "path": "/volume1/data/import/aangifte.pdf", "workset_status": "active",
            "lifecycle": None, "sensitivity": None,
        }
        payload = {"idempotency_key": str(uuid.uuid4()), "items": [{
            "file_id": 1, "category": "finance", "family": "tax_documents",
            "privacy": "medium", "manual_target_path": "",
        }]}
        with mock.patch.dict("os.environ", {"CORE_REVIEW_WRITES_ENABLED": "true"}), mock.patch.object(
            self.dashboard, "db_connect", return_value=connection,
        ), mock.patch.object(self.dashboard, "query_all", return_value=[row]):
            result = self.dashboard.create_bulk_workset_review(payload)
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        event_inserts = [sql for sql in statements if "INSERT INTO public.document_review_events" in sql]
        self.assertEqual(2, len(event_inserts))
        self.assertIn("'target_path'", event_inserts[0])
        self.assertIn("'privacy_classification'", event_inserts[1])
        self.assertEqual(1, result["document_count"])
        self.assertEqual(1, result["classification_reviews"])
        self.assertEqual(1, result["privacy_reviews"])
        self.assertFalse(result["file_mutations"])

    def test_review_is_append_only_and_does_not_update_model_or_file(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        review_id = uuid.uuid4()
        cursor.fetchone.return_value = (
            review_id, datetime(2026, 8, 11, tzinfo=timezone.utc), 1, "accepted",
        )
        row = {
            "file_id": 1, "content_group_id": uuid.uuid4(), "content_sha256": "a" * 64,
            "filename": "vacature.docx", "extension": "docx",
            "path": "/volume1/data/Documenten/CV & Sollicitaties/UWV/vacature.docx",
            "size_bytes": 42, "workset_status": "active", "category": None,
            "document_family": None, "lifecycle": None,
        }
        with mock.patch.dict("os.environ", {"CORE_REVIEW_WRITES_ENABLED": "true"}), mock.patch.object(
            self.dashboard, "db_connect", return_value=connection,
        ), mock.patch.object(
            self.dashboard, "query_one", return_value={"available": True},
        ), mock.patch.object(
            self.dashboard, "query_all", side_effect=[[row], []],
        ):
            result = self.dashboard.create_workset_review({
                "file_id": 1, "idempotency_key": str(uuid.uuid4()),
                "decision": "accepted", "corrected_category_code": "work_career",
                "corrected_document_family_code": "vacancies",
                "proposed_target_path": "/volume1/data/Persoonlijk/Actief//Werk/file.pdf",
            })
        sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("INSERT INTO public.document_review_events", sql)
        self.assertNotIn("UPDATE", sql)
        self.assertEqual(str(review_id), result["review_id"])
        self.assertFalse(result["file_mutations"])
        self.assertFalse(result["model_updates"])
        self.assertEqual("accepted", result["decision"])
        self.assertEqual("work_career", result["corrected_category_code"])
        self.assertEqual("vacancies", result["effective_target_proposal"]["document_family_code"])
        self.assertEqual("/volume1/data/Persoonlijk/Actief/Werk/file.pdf", result["proposed_target_path"])
        self.assertTrue(result["target_path_normalized"])

    def test_privacy_review_is_append_only_learning_evidence(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        review_id = uuid.uuid4()
        cursor.fetchone.return_value = (
            review_id, datetime(2026, 8, 13, tzinfo=timezone.utc), 1, "accepted",
        )
        row = {
            "file_id": 1, "content_group_id": uuid.uuid4(), "content_sha256": "b" * 64,
            "filename": "paspoort.pdf", "extension": "pdf",
            "path": "/volume1/data/Documenten/Identiteit/paspoort.pdf",
            "size_bytes": 905, "workset_status": "active", "sensitivity": None,
        }
        with mock.patch.dict("os.environ", {"CORE_REVIEW_WRITES_ENABLED": "true"}), mock.patch.object(
            self.dashboard, "db_connect", return_value=connection,
        ), mock.patch.object(
            self.dashboard, "query_one", return_value={"available": True},
        ), mock.patch.object(
            self.dashboard, "query_all", side_effect=[[row], []],
        ):
            result = self.dashboard.create_workset_review({
                "file_id": 1, "idempotency_key": str(uuid.uuid4()),
                "review_type": "privacy_classification", "decision": "accepted",
                "privacy_classification": "high",
            })
        sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("INSERT INTO public.document_review_events", sql)
        self.assertIn("'privacy_classification'", sql)
        self.assertNotIn("UPDATE", sql)
        self.assertEqual("high", result["proposal_privacy_classification"])
        self.assertEqual("high", result["privacy_classification"])
        self.assertTrue(result["learning_evidence"])
        self.assertFalse(result["file_mutations"])
        self.assertFalse(result["model_updates"])


if __name__ == "__main__":
    unittest.main()
