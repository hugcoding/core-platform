from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Sequence, TextIO

from core.config.loader import ConfigLoader


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


def main(
    argv: list[str] | None = None,
    base_path: str | Path | None = None,
    stdout: TextIO = sys.stdout,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess] = subprocess.run,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> int:
    parser = argparse.ArgumentParser(prog="core")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    subparsers.add_parser("config-json")

    docs_parser = subparsers.add_parser("docs")
    docs_parser.add_argument("action", choices=["serve", "build", "open"])

    args = parser.parse_args(argv)

    loader = ConfigLoader(base_path or _default_base_path())

    if args.command == "doctor":
        return run_doctor(loader, stdout=stdout)

    if args.command == "config-json":
        print(json.dumps(_safe_config(loader)), file=stdout)
        return 0

    if args.command == "docs":
        return run_docs(loader, args.action, stdout=stdout, runner=runner, browser_open=browser_open)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
