import io
import tempfile
import unittest
from pathlib import Path

from core.exports.csv_format import dict_reader, write_dict_rows


class CsvFormatTest(unittest.TestCase):
    def test_exports_use_semicolon_and_excel_friendly_utf8_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            write_dict_rows(
                path,
                [{"naam": "Financiën", "waarde": "1,25"}],
                ["naam", "waarde"],
            )
            raw = path.read_bytes()

        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"naam;waarde", raw)
        self.assertIn("Financiën;1,25".encode("utf-8"), raw)

    def test_reader_accepts_new_semicolon_files(self):
        handle = io.StringIO("naam;waarde\nvoorbeeld;1\n")
        self.assertEqual("voorbeeld", list(dict_reader(handle))[0]["naam"])

    def test_reader_remains_compatible_with_old_comma_files(self):
        handle = io.StringIO("naam,waarde\nvoorbeeld,1\n")
        self.assertEqual("voorbeeld", list(dict_reader(handle))[0]["naam"])


if __name__ == "__main__":
    unittest.main()
