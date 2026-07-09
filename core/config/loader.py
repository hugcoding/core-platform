from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppSettings:
    name: str
    version: str
    environment: str


@dataclass(frozen=True)
class PathsSettings:
    docs: str
    mkdocs: str
    repository: str
    nas_root: str
    nas_host: str
    nas_user: str


@dataclass(frozen=True)
class LoggingSettings:
    level: str
    format: str


@dataclass(frozen=True)
class ProjectSettings:
    key: str
    name: str
    repository: str


@dataclass(frozen=True)
class GitHubSettings:
    token: str
    owner: str


@dataclass(frozen=True)
class JiraSettings:
    url: str
    email: str
    token: str


class ConfigLoader:
    def __init__(self, base_path: str | Path = "."):
        self.base_path = Path(base_path)
        self.config_path = self.base_path / "core" / "config"
        self.secrets_path = self.base_path / "core" / "secrets"
        self.load_errors: list[str] = []

        self.core = self._load_yaml(self.config_path / "core.yaml")
        self.logging_config = self._load_yaml(self.config_path / "logging.yaml")
        self.projects = self._load_yaml(self.config_path / "projects.yaml")
        self.credentials = self._load_yaml(self.secrets_path / "credentials.yaml")

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            self.load_errors.append(f"Missing file: {path}")
            return {}

        try:
            return self._parse_simple_yaml(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            self.load_errors.append(f"Invalid YAML in {path}: {exc}")
            return {}

    def _parse_simple_yaml(self, text: str) -> dict[str, Any]:
        data: dict[str, Any] = {}
        stack: list[tuple[int, dict[str, Any]]] = [(-1, data)]

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue

            indent = len(raw_line) - len(raw_line.lstrip(" "))
            line = raw_line.strip()

            if ":" not in line:
                raise ValueError(f"line {line_number} has no key/value separator")

            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                raise ValueError(f"line {line_number} has an empty key")

            while stack and indent <= stack[-1][0]:
                stack.pop()

            parent = stack[-1][1]
            if not value:
                child: dict[str, Any] = {}
                parent[key] = child
                stack.append((indent, child))
            else:
                parent[key] = self._parse_scalar(value)

        return data

    def _parse_scalar(self, value: str) -> Any:
        if value in {"''", '""'}:
            return ""

        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            return value[1:-1]

        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered in {"null", "none", "~"}:
            return ""

        return value

    @property
    def app(self) -> AppSettings:
        data = self.core.get("app", {})
        return AppSettings(
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            environment=str(data.get("environment", "")),
        )

    @property
    def paths(self) -> PathsSettings:
        data = self.core.get("paths", {})
        return PathsSettings(
            docs=str(data.get("docs", "")),
            mkdocs=str(data.get("mkdocs", "")),
            repository=str(data.get("repository", "")),
            nas_root=str(data.get("nas_root", "")),
            nas_host=str(data.get("nas_host", "")),
            nas_user=str(data.get("nas_user", "")),
        )

    @property
    def logging(self) -> LoggingSettings:
        data = self.logging_config.get("logging", {})
        return LoggingSettings(
            level=str(data.get("level", "")),
            format=str(data.get("format", "")),
        )

    @property
    def project(self) -> ProjectSettings:
        data = self.projects.get("project", {})
        return ProjectSettings(
            key=str(data.get("key", "")),
            name=str(data.get("name", "")),
            repository=str(data.get("repository", "")),
        )

    @property
    def github(self) -> GitHubSettings:
        data = self.credentials.get("github", {})
        return GitHubSettings(
            token=str(data.get("token", "")),
            owner=str(data.get("owner", "")),
        )

    @property
    def jira(self) -> JiraSettings:
        data = self.credentials.get("jira", {})
        return JiraSettings(
            url=str(data.get("url", "")),
            email=str(data.get("email", "")),
            token=str(data.get("token", "")),
        )

    @property
    def app_name(self) -> str:
        return self.app.name

    @property
    def app_version(self) -> str:
        return self.app.version

    @property
    def log_level(self) -> str:
        return self.logging.level

    @property
    def project_key(self) -> str:
        return self.project.key

    @property
    def github_token(self) -> str:
        return self.github.token

    @property
    def github_owner(self) -> str:
        return self.github.owner

    @property
    def jira_url(self) -> str:
        return self.jira.url

    @property
    def jira_email(self) -> str:
        return self.jira.email

    @property
    def jira_token(self) -> str:
        return self.jira.token

    def validate(self) -> list[str]:
        errors = list(self.load_errors)

        required_files = [
            self.config_path / "core.yaml",
            self.config_path / "logging.yaml",
            self.config_path / "projects.yaml",
            self.secrets_path / "credentials.example.yaml",
            self.secrets_path / "credentials.yaml",
        ]

        for file in required_files:
            message = f"Missing file: {file}"
            if not file.exists() and message not in errors:
                errors.append(message)

        required_fields = [
            ("app.name", self.app.name, "core/config/core.yaml"),
            ("app.version", self.app.version, "core/config/core.yaml"),
            ("paths.docs", self.paths.docs, "core/config/core.yaml"),
            ("paths.mkdocs", self.paths.mkdocs, "core/config/core.yaml"),
            ("paths.repository", self.paths.repository, "core/config/core.yaml"),
            ("paths.nas_root", self.paths.nas_root, "core/config/core.yaml"),
            ("paths.nas_host", self.paths.nas_host, "core/config/core.yaml"),
            ("paths.nas_user", self.paths.nas_user, "core/config/core.yaml"),
            ("logging.level", self.logging.level, "core/config/logging.yaml"),
            ("project.key", self.project.key, "core/config/projects.yaml"),
            ("project.name", self.project.name, "core/config/projects.yaml"),
            ("github.token", self.github.token, "core/secrets/credentials.yaml"),
            ("github.owner", self.github.owner, "core/secrets/credentials.yaml"),
            ("jira.url", self.jira.url, "core/secrets/credentials.yaml"),
            ("jira.email", self.jira.email, "core/secrets/credentials.yaml"),
            ("jira.token", self.jira.token, "core/secrets/credentials.yaml"),
        ]

        for field, value, source in required_fields:
            if not value:
                errors.append(f"Missing required field '{field}' in {source}")

        return errors
