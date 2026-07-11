from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Sequence, TextIO

from core.config.loader import ConfigLoader
from core.integrations.jira.cache import write_cache
from core.integrations.jira.client import JiraClient, JiraClientError
from core.integrations.jira.mapper import map_search_results


def _default_base_path() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_config(loader: ConfigLoader) -> dict:
    return {
        "app": loader.app.__dict__,
        "paths": loader.paths.__dict__,
        "logging": loader.logging.__dict__,
        "project": loader.project.__dict__,
        "github": {"owner": loader.github.owner, "token_configured": bool(loader.github.token)},
        "jira": {
            "url": loader.jira.url,
            "email": loader.jira.email,
            "token_configured": bool(loader.jira.token),
        },
    }


def run_doctor(loader: ConfigLoader, stdout: TextIO = sys.stdout) -> int:
    errors = loader.validate()

    print("CORE doctor", file=stdout)
    print(f"App: {loader.app.name or 'unknown'} {loader.app.version or ''}".rstrip(), file=stdout)
    print(f"Project: {loader.project.key or 'unknown'}", file=stdout)
    print("", file=stdout)

    if errors:
        print("Configuration check: FAILED", file=stdout)
        for error in errors:
            print(f"- {error}", file=stdout)
        return 1

    print("Configuration check: OK", file=stdout)
    print("Secrets check: OK", file=stdout)
    return 0


def _mkdocs_config_path(loader: ConfigLoader) -> Path:
    configured_path = Path(loader.paths.mkdocs)
    if configured_path.is_absolute():
        return configured_path
    return loader.base_path / configured_path


def _validate_mkdocs_config(loader: ConfigLoader, stdout: TextIO) -> Path | None:
    mkdocs_config = _mkdocs_config_path(loader)
    if not loader.paths.mkdocs:
        print("MkDocs config path is missing: set paths.mkdocs in core/config/core.yaml", file=stdout)
        return None
    if not mkdocs_config.exists():
        print(f"MkDocs config not found: {mkdocs_config}", file=stdout)
        print("Configure paths.mkdocs in core/config/core.yaml or add mkdocs.yml.", file=stdout)
        return None
    return mkdocs_config


def run_docs(
    loader: ConfigLoader,
    action: str,
    stdout: TextIO = sys.stdout,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess] = subprocess.run,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> int:
    mkdocs_config = _validate_mkdocs_config(loader, stdout)
    if mkdocs_config is None:
        return 1

    if action == "open":
        url = "http://127.0.0.1:8000"
        print(f"Opening {url}", file=stdout)
        return 0 if browser_open(url) else 1

    commands = {
        "serve": ["mkdocs", "serve", "-f", str(mkdocs_config), "-a", "127.0.0.1:8000"],
        "build": ["mkdocs", "build", "-f", str(mkdocs_config)],
    }

    try:
        completed = runner(commands[action])
    except FileNotFoundError:
        print("MkDocs command not found. Install MkDocs and run it through `core docs ...`.", file=stdout)
        return 1

    return completed.returncode


def _jira_client(loader: ConfigLoader, opener=None) -> JiraClient:
    if opener is None:
        return JiraClient(loader.jira.url, loader.jira.email, loader.jira.token)
    return JiraClient(loader.jira.url, loader.jira.email, loader.jira.token, opener=opener)


def _jira_credentials_errors(loader: ConfigLoader) -> list[str]:
    errors = []
    if not loader.jira.url:
        errors.append("Missing Jira URL: set jira.url in core/secrets/credentials.yaml")
    if not loader.jira.email:
        errors.append("Missing Jira email: set jira.email in core/secrets/credentials.yaml")
    if not loader.jira.token:
        errors.append("Missing Jira token: set jira.token in core/secrets/credentials.yaml")
    return errors


def _jira_project(loader: ConfigLoader, project: str | None) -> str:
    return project or loader.project.key


def _jira_jql(kind: str, project: str) -> str:
    if kind == "epics":
        return f'project = "{project}" AND issuetype = Epic ORDER BY created DESC'
    if kind == "stories":
        return f'project = "{project}" AND issuetype in (Story, Task, Bug) ORDER BY created DESC'
    return f'project = "{project}" ORDER BY updated DESC'


def run_jira(
    loader: ConfigLoader,
    action: str,
    stdout: TextIO = sys.stdout,
    opener=None,
    project: str | None = None,
    limit: int = 50,
    dry_run: bool = False,
    use_cache: bool = True,
) -> int:
    credential_errors = _jira_credentials_errors(loader)
    if credential_errors:
        for error in credential_errors:
            print(error, file=stdout)
        return 1

    if action == "auth":
        try:
            myself = _jira_client(loader, opener=opener).myself()
        except JiraClientError as exc:
            print(str(exc), file=stdout)
            return 1
        display_name = myself.get("displayName") or myself.get("emailAddress") or "unknown"
        print(f"Jira authentication OK: {display_name}", file=stdout)
        return 0

    selected_project = _jira_project(loader, project)
    jql = _jira_jql(action, selected_project)

    if action == "sync":
        print("Jira sync plan", file=stdout)
        print("Mode: dry-run" if dry_run else "Mode: read-only cache refresh", file=stdout)
        for kind in ["epics", "stories"]:
            print(f"- {kind}: {_jira_jql(kind, selected_project)}", file=stdout)
        return 0

    if dry_run:
        print("Jira dry-run", file=stdout)
        print(f"Project: {selected_project}", file=stdout)
        print(f"JQL: {jql}", file=stdout)
        print(f"Limit: {limit}", file=stdout)
        return 0

    try:
        payload = _jira_client(loader, opener=opener).search(jql, max_results=limit)
    except JiraClientError as exc:
        print(str(exc), file=stdout)
        return 1

    mapped = map_search_results(payload)
    print(f"Jira {action}: {len(mapped['issues'])} issues fetched of {mapped['total']} total", file=stdout)
    for issue in mapped["issues"]:
        print(f"- {issue['key']} [{issue['status']}] {issue['summary']}", file=stdout)

    if use_cache:
        cache_path = write_cache(loader.base_path, action, mapped)
        print(f"Cache written: {cache_path}", file=stdout)

    return 0


def main(
    argv: list[str] | None = None,
    base_path: str | Path | None = None,
    stdout: TextIO = sys.stdout,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess] = subprocess.run,
    browser_open: Callable[[str], bool] = webbrowser.open,
    jira_opener=None,
) -> int:
    parser = argparse.ArgumentParser(prog="core")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    subparsers.add_parser("config-json")

    docs_parser = subparsers.add_parser("docs")
    docs_parser.add_argument("action", choices=["serve", "build", "open"])

    jira_parser = subparsers.add_parser("jira")
    jira_parser.add_argument("action", choices=["auth", "epics", "stories", "sync"])
    jira_parser.add_argument("--project")
    jira_parser.add_argument("--limit", type=int, default=50)
    jira_parser.add_argument("--dry-run", action="store_true")
    jira_parser.add_argument("--no-cache", action="store_true")

    args = parser.parse_args(argv)

    loader = ConfigLoader(base_path or _default_base_path())

    if args.command == "doctor":
        return run_doctor(loader, stdout=stdout)

    if args.command == "config-json":
        print(json.dumps(_safe_config(loader)), file=stdout)
        return 0

    if args.command == "docs":
        return run_docs(loader, args.action, stdout=stdout, runner=runner, browser_open=browser_open)

    if args.command == "jira":
        return run_jira(
            loader,
            args.action,
            stdout=stdout,
            opener=jira_opener,
            project=args.project,
            limit=args.limit,
            dry_run=args.dry_run,
            use_cache=not args.no_cache,
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
