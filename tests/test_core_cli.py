import io
import tempfile
import unittest
from pathlib import Path

from core.cli import main
from tests.test_config_loader import (
    CORE_YAML,
    CREDENTIALS_EXAMPLE_YAML,
    CREDENTIALS_YAML,
    LOGGING_YAML,
    PROJECTS_YAML,
)


def write_config(root: Path, credentials: str | None = CREDENTIALS_YAML) -> None:
    config_dir = root / "core" / "config"
    secrets_dir = root / "core" / "secrets"
    config_dir.mkdir(parents=True)
    secrets_dir.mkdir(parents=True)

    (config_dir / "core.yaml").write_text(CORE_YAML, encoding="utf-8")
    (config_dir / "logging.yaml").write_text(LOGGING_YAML, encoding="utf-8")
    (config_dir / "projects.yaml").write_text(PROJECTS_YAML, encoding="utf-8")
    (secrets_dir / "credentials.example.yaml").write_text(CREDENTIALS_EXAMPLE_YAML, encoding="utf-8")
    if credentials is not None:
        (secrets_dir / "credentials.yaml").write_text(credentials, encoding="utf-8")


class CoreCliDoctorTest(unittest.TestCase):
    def test_core_doctor_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            stdout = io.StringIO()

            exit_code = main(["doctor"], base_path=root, stdout=stdout)

            self.assertEqual(0, exit_code)
            self.assertIn("Configuration check: OK", stdout.getvalue())
            self.assertIn("Secrets check: OK", stdout.getvalue())

    def test_core_doctor_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root, credentials=None)
            stdout = io.StringIO()

            exit_code = main(["doctor"], base_path=root, stdout=stdout)

            self.assertEqual(1, exit_code)
            self.assertIn("Configuration check: FAILED", stdout.getvalue())
            self.assertIn("credentials.yaml", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
