"""Tests for the optional Claude reasoning annotator."""

from __future__ import annotations

from stable_depeg_radar.detector import DepegSignal
from stable_depeg_radar.reasoning import _DISABLED_HINT, annotate_with_reasoning


def _signal(symbol="USDC", dev=-150.0):
    return DepegSignal(
        chain="ethereum",
        token=symbol,
        address="0xa",
        observed_price_usd=1 + dev / 10_000,
        deviation_bps=dev,
        sample_count=5,
        block_time_range=("a", "b"),
        severity="warning",
    )


class _Block:
    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, response_text):
        self._text = response_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Resp(self._text)


class _FakeClient:
    def __init__(self, response_text):
        self.messages = _FakeMessages(response_text)


def test_annotate_no_signals_is_noop():
    out = annotate_with_reasoning([])
    assert out == []


def test_annotate_without_api_key_attaches_hint(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sigs = [_signal()]
    out = annotate_with_reasoning(sigs)
    assert out is sigs
    assert sigs[0].reasoning == _DISABLED_HINT


def test_annotate_with_injected_client_pairs_lines_to_signals():
    sigs = [_signal("USDC", -150.0), _signal("USDe", -500.0)]
    response_text = "USDC: Curve pool imbalance.\nUSDe: Funding rate stress."
    fake = _FakeClient(response_text)
    annotate_with_reasoning(sigs, client=fake, model="claude-test")
    assert sigs[0].reasoning == "USDC: Curve pool imbalance."
    assert sigs[1].reasoning == "USDe: Funding rate stress."
    # Model override propagated through.
    assert fake.messages.calls[0]["model"] == "claude-test"


def test_annotate_handles_short_response_gracefully():
    sigs = [_signal("USDC"), _signal("USDe")]
    fake = _FakeClient("USDC: only one explanation.")
    annotate_with_reasoning(sigs, client=fake)
    assert sigs[0].reasoning == "USDC: only one explanation."
    # Second signal stays un-annotated rather than mis-aligning.
    assert sigs[1].reasoning is None
