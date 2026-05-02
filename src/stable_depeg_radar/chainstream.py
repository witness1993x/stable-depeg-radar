"""Minimal stdlib-only ChainStream GraphQL client.

Mirrors the framework's ``http_json`` + ``post_chainstream_graphql`` pattern in
``agentflow_pipeline/cli.py`` so the radar can run without pulling in
``requests`` / ``aiohttp``. Tests inject a fake by monkey-patching
:func:`urllib.request.urlopen`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

DEFAULT_USER_AGENT = "stable-depeg-radar/0.1.0"
DEFAULT_ENDPOINT = "https://graphql.chainstream.io/graphql"


class ChainStreamError(RuntimeError):
    """Raised on transport, HTTP, or GraphQL errors from ChainStream."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        graphql_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.graphql_errors = graphql_errors or []


@dataclass(slots=True)
class GraphQLResponse:
    data: dict[str, Any]
    errors: list[dict[str, Any]]
    extensions: dict[str, Any]


class ChainStreamClient:
    """Tiny synchronous GraphQL client over urllib (stdlib only).

    Parameters
    ----------
    endpoint:
        GraphQL endpoint, e.g. ``https://graphql.chainstream.io/graphql``.
    api_key:
        Sent as ``X-API-KEY`` header.
    user_agent:
        Override the User-Agent string. Useful for usage analytics.
    timeout:
        Per-request timeout in seconds.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 30.0,
    ) -> None:
        if not endpoint:
            raise ChainStreamError("ChainStream endpoint is required")
        if not api_key:
            raise ChainStreamError("ChainStream API key is required")
        self.endpoint = endpoint
        self.api_key = api_key
        self.user_agent = user_agent
        self.timeout = timeout

    def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> GraphQLResponse:
        body = json.dumps(
            {"query": query, "variables": variables or {}},
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-KEY": self.api_key,
            "User-Agent": self.user_agent,
        }
        req = request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                status = getattr(response, "status", 200)
        except error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:  # pragma: no cover - defensive
                pass
            raise ChainStreamError(
                f"HTTP {exc.code} from ChainStream: {detail[:240]}",
                status=exc.code,
            ) from exc
        except error.URLError as exc:
            raise ChainStreamError(
                f"Unable to reach {self.endpoint}: {exc.reason}",
            ) from exc

        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ChainStreamError(
                f"Unable to parse JSON from ChainStream: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise ChainStreamError("Unexpected non-object GraphQL response")

        errors = payload.get("errors") or []
        if errors:
            messages = "; ".join(
                str(e.get("message", "<no message>"))
                for e in errors
                if isinstance(e, dict)
            )
            raise ChainStreamError(
                f"GraphQL errors: {messages}",
                status=status,
                graphql_errors=[e for e in errors if isinstance(e, dict)],
            )

        return GraphQLResponse(
            data=payload.get("data") or {},
            errors=[],
            extensions=payload.get("extensions") or {},
        )
