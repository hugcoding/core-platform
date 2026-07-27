import unittest

from tools.runtime.copy_plan import choose_bucket, plan_rows, safe_filename


def row(action, path, hash_content="hash-1", sensitivity="normal", source_paths="[]"):
    return {
        "representative_file_id": "1",
        "hash_content": hash_content,
        "representative_path": path,
        "source_paths": source_paths,
        "proposal_action": action,
        "copy_readiness": "ready_for_copy_plan",
        "sensitivity": sensitivity,
    }


class CopyPlanTest(unittest.TestCase):
    def test_standard_buckets_use_all_source_evidence(self):
        item = row(
            "document_standard",
            "/volume1/source/report.pdf",
            source_paths='["/volume1/backup/Documents/Studie/report.pdf"]',
        )
        self.assertEqual("documents/study", choose_bucket(item)[0])

    def test_sensitive_documents_are_separated(self):
        item = row("document_sensitive", "/volume1/Documents/Belasting/aanslag.pdf")
        self.assertEqual("sensitive/finance", choose_bucket(item)[0])
        planned = plan_rows([item], "/volume1/data")[0]
        self.assertEqual("blocked_sensitive_policy", planned["semantic_scope"])

    def test_unclear_document_is_unsorted_and_not_copy_candidate(self):
        planned = plan_rows(
            [row("document_standard", "/volume1/backup/NITRO/D/data/hugo/Documents/report.pdf")],
            "/volume1/data",
        )[0]
        self.assertEqual("documents/unsorted", planned["target_bucket"])
        self.assertEqual("manual_target_review", planned["copy_action"])

    def test_different_hashes_at_same_target_are_blocked(self):
        rows = [
            row("document_standard", "/volume1/Documents/Studie/report.pdf", "hash-1"),
            row("document_standard", "/volume1/Other/studie/REPORT.PDF", "hash-2"),
        ]
        planned = plan_rows(rows, "/volume1/data")
        self.assertEqual({"name_collision"}, {item["collision_status"] for item in planned})
        self.assertEqual({"blocked_name_collision"}, {item["copy_action"] for item in planned})

    def test_non_document_groups_are_not_planned(self):
        self.assertEqual(
            [],
            plan_rows([row("retain_project_technical", "/volume1/source/code.java")], "/volume1/data"),
        )

    def test_filename_is_smb_safe(self):
        self.assertEqual("report_2026_.pdf", safe_filename('/volume1/source/report:2026?.pdf'))
        self.assertEqual("_CON.txt", safe_filename("/volume1/source/CON.txt"))


if __name__ == "__main__":
    unittest.main()
