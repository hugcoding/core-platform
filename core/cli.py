from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

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


def main(argv: list[str] | None = None, base_path: str | Path | None = None, stdout: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="core")
    parser.add_argument("command", choices=["doctor", "config-json"])
    args = parser.parse_args(argv)

    loader = ConfigLoader(base_path or _default_base_path())

    if args.command == "doctor":
        return run_doctor(loader, stdout=stdout)

    if args.command == "config-json":
        print(json.dumps(_safe_config(loader)), file=stdout)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
