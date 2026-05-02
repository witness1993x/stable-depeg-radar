"""Shared pytest fixtures for stable-depeg-radar."""

from __future__ import annotations

import json
from io import BytesIO

import pytest

from stable_depeg_radar.detector import Observation


@pytest.fixture
def usdt_eth_address() -> str:
    return "0xdac17f958d2ee523a2206206994597c13d831ec7"


@pytest.fixture
def usdc_eth_address() -> str:
    return "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"


@pytest.fixture
def usde_eth_address() -> str:
    return "0x4c9edd5852cd905f086c759e8383e09bff1e68b3"


@pytest.fixture
def stable_observations(usdt_eth_address, usdc_eth_address, usde_eth_address):
    """A representative mixed-severity observation set."""
    return [
        # USDT @ ~1.0001 — below info threshold (1 bp)
        Observation("ethereum", usdt_eth_address, "USDT", 1.0001, "2026-05-02T00:00:00Z"),
        Observation("ethereum", usdt_eth_address, "USDT", 1.0002, "2026-05-02T00:01:00Z"),
        # USDC @ ~0.997 — info / warn boundary (-30 bps)
        Observation("ethereum", usdc_eth_address, "USDC", 0.9970, "2026-05-02T00:00:00Z"),
        Observation("ethereum", usdc_eth_address, "USDC", 0.9970, "2026-05-02T00:01:00Z"),
        # USDe @ 0.95 — critical (-500 bps)
        Observation("ethereum", usde_eth_address, "USDe", 0.95, "2026-05-02T00:00:30Z"),
        Observation("ethereum", usde_eth_address, "USDe", 0.95, "2026-05-02T00:01:30Z"),
        Observation("ethereum", usde_eth_address, "USDe", 0.95, "2026-05-02T00:02:30Z"),
    ]


class _FakeURLOpenResponse:
    """A minimal stand-in for `urllib.request.urlopen()`'s return value."""

    def __init__(self, payload: dict, status: int = 200) -> None:
        self._buf = BytesIO(json.dumps(payload).encode("utf-8"))
        self.status = status

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._buf.close()
        return False


@pytest.fixture
def fake_urlopen_factory():
    """Factory that returns a callable suitable for monkeypatching urlopen.

    Usage::

        captured = {}
        def opener(req, timeout=30):
            captured["req"] = req
            return _FakeURLOpenResponse({"data": {...}})
        monkeypatch.setattr("urllib.request.urlopen", opener)
    """

    def _build(payload: dict, *, status: int = 200, captured: dict | None = None):
        def _opener(req, timeout=30):
            if captured is not None:
                captured["req"] = req
                captured["timeout"] = timeout
            return _FakeURLOpenResponse(payload, status=status)

        return _opener

    return _build
