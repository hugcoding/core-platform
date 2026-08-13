import unittest
from core.organization.path_normalization import normalize_target_path

class PathNormalizationTests(unittest.TestCase):
    def test_duplicate_separators_are_collapsed(self):
        result = normalize_target_path("/volume1/data/Persoonlijk/Actief//Werk/file.pdf")
        self.assertEqual("/volume1/data/Persoonlijk/Actief/Werk/file.pdf", result["normalized"])
        self.assertTrue(result["changed"])

    def test_unsafe_or_unmanaged_paths_are_rejected(self):
        for value in ("relative/file.pdf", "/volume1/data/Persoonlijk/../secret.pdf", "/etc/passwd"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_target_path(value)
