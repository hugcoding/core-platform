from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class JiraClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class JiraClient:
    base_url: str
    email: str
    token: str
    opener: Callable[[Request, int], Any] = urlopen
    timeout: int = 30

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    def _auth_header(self) -> str:
        raw = f"{self.email}:{self.token}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = ""
        if params:
            query = "?" + urlencode(params)

        request = Request(
            self.base_url + path + query,
            headers={
                "Authorization": self._auth_header(),
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            response = self.opener(request, timeout=self.timeout)
            with response:
                body = response.read().decode("utf-8")
        except Exception as exc:
            raise JiraClientError(f"Jira request failed: {exc}") from exc

        try:
            return json.loads(body or "{}")
        except json.JSONDecodeError as exc:
            raise JiraClientError("Jira returned invalid JSON") from exc

    def myself(self) -> dict[str, Any]:
        return self._request("/rest/api/3/myself")

    def search(self, jql: str, max_results: int = 50) -> dict[str, Any]:
        fields = "summary,status,issuetype,labels,assignee,priority,parent,updated,created"
        return self._request(
            "/rest/api/3/search/jql",
            {
                "jql": jql,
                "maxResults": max_results,
                "fields": fields,
            },
        )
