import unittest

from tools.runtime.migration_proposal import propose


def row(review_class, extension, sensitivity="normal", category="unknown", path="/volume1/source/file"):
    return {
        "hash_content": "abc",
        "review_class": review_class,
        "representative_extension": extension,
        "sensitivity": sensitivity,
        "category": category,
        "representative_path": path,
    }


class MigrationProposalTest(unittest.TestCase):
    def test_document_waves_are_split_by_sensitivity(self):
        self.assertEqual("document_standard", propose(row("personal_document", "docx"))[0])
        self.assertEqual(
            "document_sensitive",
            propose(row("personal_document", "pdf", sensitivity="sensitive"))[0],
        )

    def test_missing_hash_blocks_copy_planning(self):
        item = row("personal_document", "docx")
        item["hash_content"] = ""
        self.assertEqual(("manual_review", "blocked_missing_hash"), propose(item)[:2])

    def test_cisco_eps_is_retained_as_technical(self):
        item = row(
            "manual_review",
            "eps",
            path="/volume1/backup/Documents/studie/cisco icons/3015_eps/router.eps",
        )
        self.assertEqual("retain_project_technical", propose(item)[0])

    def test_archive_and_cloud_pointer_remain_separate(self):
        self.assertEqual(
            "inspect_archive",
            propose(row("manual_review", "zip", category="archive_review"))[0],
        )
        self.assertEqual("recover_cloud_pointer", propose(row("manual_review", "gdoc"))[0])

    def test_media_is_deferred(self):
        self.assertEqual("deferred_media", propose(row("deferred_media", "jpg"))[0])


if __name__ == "__main__":
    unittest.main()
