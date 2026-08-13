import unittest
from core.organization.path_normalization import normalize_target_path, suggest_known_target_path

class PathNormalizationTests(unittest.TestCase):
    def test_duplicate_separators_are_collapsed(self):
        result = normalize_target_path("/volume1/data/Persoonlijk/Actief//Werk/file.pdf")
        self.assertEqual("/volume1/data/Persoonlijk/Actief/Werk/file.pdf", result["normalized"])
        self.assertTrue(result["changed"])

    def test_unsafe_or_unmanaged_paths_are_rejected(self):
        for value in ("relative/file.pdf", "/volume1/data/Persoonlijk/../secret.pdf", "/etc/passwd"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_target_path(value)

    def test_destination_directory_gets_existing_filename(self):
        result = normalize_target_path(
            "/volume1/data/Persoonlijk/Actief/Geldzaken/Belasting",
            filename="aangifte.pdf",
        )
        self.assertEqual("directory", result["input_kind"])
        self.assertEqual(
            "/volume1/data/Persoonlijk/Actief/Geldzaken/Belasting/aangifte.pdf",
            result["normalized"],
        )

    def test_close_confirmed_segment_requires_explicit_confirmation(self):
        result = suggest_known_target_path(
            "/volume1/data/Persoonlijk/Actief/Geldzaken/Belastingen",
            filename="aangifte.pdf",
            known_paths=[
                "/volume1/data/Persoonlijk/Actief/Geldzaken/Belasting/vorig.pdf",
            ],
        )
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(
            "/volume1/data/Persoonlijk/Actief/Geldzaken/Belasting/aangifte.pdf",
            result["suggestion"],
        )

    def test_different_filename_is_not_silently_rewritten(self):
        result = normalize_target_path(
            "/volume1/data/Persoonlijk/Actief/Geldzaken/Belasting/nieuw.pdf",
            filename="oud.pdf",
        )
        self.assertEqual("full_path", result["input_kind"])
        self.assertEqual("nieuw.pdf", result["normalized"].rsplit("/", 1)[-1])

    def test_confirmed_casing_is_a_technical_normalization(self):
        result = suggest_known_target_path(
            "/volume1/data/Persoonlijk/Actief/geldzaken/belasting",
            filename="aangifte.pdf",
            known_paths=["/volume1/data/Persoonlijk/Actief/Geldzaken/Belasting/vorig.pdf"],
        )
        self.assertTrue(result["technical_normalization"])
        self.assertFalse(result["requires_confirmation"])
        self.assertIn("/Geldzaken/Belasting/", result["suggestion"])
