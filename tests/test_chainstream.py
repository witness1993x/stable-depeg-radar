"""Tests for the stdlib GraphQL client (urllib monkey-patched)."""

from __future__ import annotations

import json
from io import BytesIO

import pytest

from stable_depeg_radar.chainstream import (
    DEFAULT_ENDPOINT,
    ChainStreamClient,
    ChainStreamError,
)


class _Resp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._buf = BytesIO(json.dumps(payload).encode("utf-8"))
        self.status = status

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._buf.close()
        return False


def test_constructor_rejects_missing_endpoint():
    with pytest.raises(ChainStreamError):
        ChainStreamClient(endpoint="", api_key="k")


def test_constructor_rejects_missing_api_key():
    with pytest.raises(ChainStreamError):
        ChainStreamClient(endpoint=DEFAULT_ENDPOINT, api_key="")


def test_query_posts_with_required_headers_and_body(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = req.data
        captured["method"] = req.get_method()
        return _Resp({"data": {"ok": 1}})

    monkeypatch.setattr("stable_depeg_radar.chainstream.request.urlopen", fake_urlopen)

    client = ChainStreamClient(DEFAULT_ENDPOINT, "secret-key")
    response = client.query("query { ok }", variables={"x": 1})

    assert response.data == {"ok": 1}
    assert captured["url"] == DEFAULT_ENDPOINT
    assert captured["method"] == "POST"
    # urllib normalises header names to title case
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers["x-api-key"] == "secret-key"
    assert headers["content-type"].startswith("application/json")
    body = json.loads(captured["body"])
    assert body == {"query": "query { ok }", "variables": {"x": 1}}


def test_query_raises_on_graphql_errors(monkeypatch):
    def fake_urlopen(req, timeout=30):
        return _Resp({"errors": [{"message": "bad query"}]})

    monkeypatch.setattr("stable_depeg_radar.chainstream.request.urlopen", fake_urlopen)
    client = ChainStreamClient(DEFAULT_ENDPOINT, "k")
    with pytest.raises(ChainStreamError) as excinfo:
        client.query("{ x }")
    assert "bad query" in str(excinfo.value)


def test_query_raises_on_invalid_json(monkeypatch):
    class BadResp(_Resp):
        def read(self):  # type: ignore[override]
            return b"not-json"

    def fake_urlopen(req, timeout=30):
        return BadResp({})

    monkeypatch.setattr("stable_depeg_radar.chainstream.request.urlopen", fake_urlopen)
    client = ChainStreamClient(DEFAULT_ENDPOINT, "k")
    with pytest.raises(ChainStreamError) as excinfo:
        client.query("{ x }")
    assert "parse JSON" in str(excinfo.value)


def test_query_returns_extensions(monkeypatch):
    def fake_urlopen(req, timeout=30):
        return _Resp(
            {
                "data": {"x": 1},
                "extensions": {"credits": {"total": 12, "unit": "request"}},
            }
        )

    monkeypatch.setattr("stable_depeg_radar.chainstream.request.urlopen", fake_urlopen)
    client = ChainStreamClient(DEFAULT_ENDPOINT, "k")
    response = client.query("{ x }")
    assert response.extensions["credits"]["total"] == 12
