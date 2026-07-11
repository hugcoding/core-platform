import io
import json
import tempfile
import unittest
from pathlib import Path

from core.cli import main
from core.integrations.jira.mapper import map_issue
from tests.test_core_cli import write_config


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class JiraCliTest(unittest.TestCase):
    def test_jira_auth_uses_configured_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            calls = []
            stdout = io.StringIO()

            def opener(request, timeout):
                calls.append((request, timeout))
                return FakeResponse({"displayName": "Hugo"})

            exit_code = main(["jira", "auth"], base_path=root, stdout=stdout, jira_opener=opener)

            self.assertEqual(0, exit_code)
            self.assertIn("Jira authentication OK: Hugo", stdout.getvalue())
            self.assertEqual("https://example.atlassian.net/rest/api/3/myself", calls[0][0].full_url)
            self.assertEqual("Basic dXNlckBleGFtcGxlLmNvbTpqaXJhLXRva2Vu", calls[0][0].headers["Authorization"])

    def test_jira_epics_dry_run_prints_jql_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            stdout = io.StringIO()

            exit_code = main(
                ["jira", "epics", "--project", "SCRUM", "--limit", "25", "--dry-run"],
                base_path=root,
                stdout=stdout,
            )

            self.assertEqual(0, exit_code)
            self.assertIn("Project: SCRUM", stdout.getvalue())
            self.assertIn('project = "SCRUM" AND issuetype = Epic', stdout.getvalue())
            self.assertIn("Limit: 25", stdout.getvalue())

    def test_jira_stories_fetch_maps_and_writes_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            stdout = io.StringIO()

            calls = []

            def opener(request, timeout):
                calls.append(request)
                return FakeResponse(
                    {
                        "startAt": 0,
                        "maxResults": 1,
                        "total": 1,
                        "issues": [
                            {
                                "id": "10000",
                                "key": "SCRUM-1",
                                "fields": {
                                    "summary": "ADR Engine",
                                    "issuetype": {"name": "Story"},
                                    "status": {"name": "Done"},
                                    "priority": {"name": "Medium"},
                                    "assignee": {"displayName": "Hugo"},
                                    "labels": ["core"],
                                    "created": "2026-07-01T00:00:00.000+0000",
                                    "updated": "2026-07-02T00:00:00.000+0000",
                                },
                            }
                        ],
                    }
                )

            exit_code = main(
                ["jira", "stories", "--project", "SCRUM", "--limit", "1"],
                base_path=root,
                stdout=stdout,
                jira_opener=opener,
            )

            self.assertEqual(0, exit_code)
            self.assertIn("Jira stories: 1 issues fetched of 1 total", stdout.getvalue())
            self.assertIn("SCRUM-1 [Done] ADR Engine", stdout.getvalue())
            self.assertIn("/rest/api/3/search/jql", calls[0].full_url)
            cache_path = root / "core" / "cache" / "jira" / "stories.json"
            self.assertTrue(cache_path.exists())
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual("SCRUM-1", cached["issues"][0]["key"])

    def test_jira_sync_is_read_only_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            stdout = io.StringIO()

            exit_code = main(["jira", "sync", "--project", "SCRUM", "--dry-run"], base_path=root, stdout=stdout)

            self.assertEqual(0, exit_code)
            self.assertIn("Jira sync plan", stdout.getvalue())
            self.assertIn("Mode: dry-run", stdout.getvalue())
            self.assertIn("epics", stdout.getvalue())
            self.assertIn("stories", stdout.getvalue())


class JiraMapperTest(unittest.TestCase):
    def test_map_issue_handles_missing_optional_fields(self):
        issue = {"id": "1", "key": "SCRUM-1", "fields": {"summary": "Test"}}

        mapped = map_issue(issue)

        self.assertEqual("SCRUM-1", mapped["key"])
        self.assertEqual("Test", mapped["summary"])
        self.assertEqual("", mapped["status"])
        self.assertEqual([], mapped["labels"])


if __name__ == "__main__":
    unittest.main()
