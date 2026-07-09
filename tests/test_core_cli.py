import io
import subprocess
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


def write_config(root: Path, credentials: str | None = CREDENTIALS_YAML, mkdocs: bool = True) -> None:
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
    if mkdocs:
        (root / "mkdocs.yml").write_text("site_name: Test\n", encoding="utf-8")


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


class CoreCliDocsTest(unittest.TestCase):
    def test_docs_serve_runs_mkdocs_serve_with_configured_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            calls = []

            def runner(command):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0)

            exit_code = main(["docs", "serve"], base_path=root, runner=runner)

            self.assertEqual(0, exit_code)
            self.assertEqual(
                [["mkdocs", "serve", "-f", str(root / "mkdocs.yml"), "-a", "127.0.0.1:8000"]],
                calls,
            )

    def test_docs_build_runs_mkdocs_build_with_configured_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            calls = []

            def runner(command):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0)

            exit_code = main(["docs", "build"], base_path=root, runner=runner)

            self.assertEqual(0, exit_code)
            self.assertEqual([["mkdocs", "build", "-f", str(root / "mkdocs.yml")]], calls)

    def test_docs_open_opens_local_mkdocs_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            opened = []
            stdout = io.StringIO()

            def browser_open(url):
                opened.append(url)
                return True

            exit_code = main(["docs", "open"], base_path=root, stdout=stdout, browser_open=browser_open)

            self.assertEqual(0, exit_code)
            self.assertEqual(["http://127.0.0.1:8000"], opened)
            self.assertIn("Opening http://127.0.0.1:8000", stdout.getvalue())

    def test_docs_command_fails_when_mkdocs_config_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root, mkdocs=False)
            calls = []
            stdout = io.StringIO()

            def runner(command):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0)

            exit_code = main(["docs", "build"], base_path=root, stdout=stdout, runner=runner)

            self.assertEqual(1, exit_code)
            self.assertEqual([], calls)
            self.assertIn("MkDocs config not found", stdout.getvalue())
            self.assertIn("core/config/core.yaml", stdout.getvalue())

    def test_docs_command_reports_missing_mkdocs_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            stdout = io.StringIO()

            def runner(command):
                raise FileNotFoundError

            exit_code = main(["docs", "build"], base_path=root, stdout=stdout, runner=runner)

            self.assertEqual(1, exit_code)
            self.assertIn("MkDocs command not found", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
