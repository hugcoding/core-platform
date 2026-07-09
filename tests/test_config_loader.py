import tempfile
import unittest
from pathlib import Path
from typing import Optional

from core.config.loader import ConfigLoader


CORE_YAML = """app:
  name: CORE Platform
  version: 3.0
  environment: test
paths:
  docs: docs
  mkdocs: mkdocs.yml
  repository: '\\\\NAS\\docker\\nas-stack'
  nas_root: /volume1/docker/nas-stack
  nas_host: NAS
  nas_user: hugo
"""

LOGGING_YAML = """logging:
  level: INFO
  format: '%(levelname)s:%(message)s'
"""

PROJECTS_YAML = """project:
  key: CORE
  name: CORE Platform
  repository: core-platform
"""

CREDENTIALS_YAML = """github:
  token: gh-token
  owner: hugo
jira:
  url: https://example.atlassian.net
  email: user@example.com
  token: jira-token
"""

CREDENTIALS_EXAMPLE_YAML = """github:
  token: your-github-token
  owner: your-github-owner
jira:
  url: https://your-domain.atlassian.net
  email: your-email@example.com
  token: your-jira-api-token
"""


class ConfigLoaderTest(unittest.TestCase):
    def write_config(self, root: Path, credentials: Optional[str] = CREDENTIALS_YAML) -> None:
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

    def test_successful_config_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_config(root)

            loader = ConfigLoader(root)

            self.assertEqual([], loader.validate())
            self.assertEqual("CORE Platform", loader.app.name)
            self.assertEqual("/volume1/docker/nas-stack", loader.paths.nas_root)
            self.assertEqual("CORE", loader.project.key)
            self.assertEqual("hugo", loader.github.owner)
            self.assertEqual("https://example.atlassian.net", loader.jira.url)

    def test_missing_credentials_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_config(root, credentials=None)

            errors = ConfigLoader(root).validate()

            self.assertTrue(any("credentials.yaml" in error for error in errors))
            self.assertTrue(any("Missing file" in error for error in errors))

    def test_missing_required_github_and_jira_fields(self):
        credentials = """github:
  token: ''
  owner: ''
jira:
  url: ''
  email: ''
  token: ''
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_config(root, credentials=credentials)

            errors = ConfigLoader(root).validate()

            self.assertIn("Missing required field 'github.token' in core/secrets/credentials.yaml", errors)
            self.assertIn("Missing required field 'github.owner' in core/secrets/credentials.yaml", errors)
            self.assertIn("Missing required field 'jira.url' in core/secrets/credentials.yaml", errors)
            self.assertIn("Missing required field 'jira.email' in core/secrets/credentials.yaml", errors)
            self.assertIn("Missing required field 'jira.token' in core/secrets/credentials.yaml", errors)


if __name__ == "__main__":
    unittest.main()
