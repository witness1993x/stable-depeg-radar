"""Tests for the pretty + JSON formatters."""

from __future__ import annotations

import json

from stable_depeg_radar.detector import DepegSignal
from stable_depeg_radar.format import format_json, format_pretty, signal_to_dict


def _signal(severity="warning", *, dev_bps=-150.0, token="USDC"):
    return DepegSignal(
        chain="ethereum",
        token=token,
        address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        observed_price_usd=1.0 + dev_bps / 10_000.0,
        deviation_bps=dev_bps,
        sample_count=12,
        block_time_range=("2026-05-02T00:00:00Z", "2026-05-02T00:14:00Z"),
        severity=severity,  # type: ignore[arg-type]
    )


def test_format_pretty_no_signals_says_ok():
    text = format_pretty([], color=False)
    assert "OK" in text
    assert "no stablecoin depeg" in text


def test_format_pretty_includes_token_severity_chain_and_address():
    text = format_pretty([_signal()], color=False)
    assert "USDC" in text
    assert "WARN" in text
    assert "ethereum" in text
    assert "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48" in text


def test_format_pretty_uses_color_when_enabled():
    colored = format_pretty([_signal(severity="critical", dev_bps=-500)], color=True)
    plain = format_pretty([_signal(severity="critical", dev_bps=-500)], color=False)
    assert "\x1b[" in colored
    assert "\x1b[" not in plain


def test_format_pretty_renders_arrow_for_below_peg():
    text = format_pretty([_signal(dev_bps=-79.0)], color=False)
    assert "v" in text  # below-peg arrow


def test_format_pretty_renders_arrow_for_above_peg():
    text = format_pretty([_signal(dev_bps=120.0)], color=False)
    assert "^" in text


def test_format_pretty_includes_reasoning_line():
    sig = _signal()
    sig.reasoning = "USDC drift driven by Curve pool imbalance."
    text = format_pretty([sig], color=False)
    assert "reasoning:" in text
    assert "Curve pool" in text


def test_format_pretty_header():
    text = format_pretty([_signal()], color=False, header="my header")
    assert text.startswith("my header")


def test_format_json_schema_envelope():
    text = format_json([_signal()], indent=None)
    payload = json.loads(text)
    assert payload["schema"] == "stable-depeg-radar/v1"
    assert payload["signal_count"] == 1
    assert isinstance(payload["signals"], list)


def test_format_json_signal_keys_and_rounding():
    text = format_json([_signal(dev_bps=-79.123456)])
    payload = json.loads(text)
    sig = payload["signals"][0]
    assert sig["chain"] == "ethereum"
    assert sig["token"] == "USDC"
    assert sig["severity"] == "warning"
    assert isinstance(sig["block_time_range"], list)
    assert sig["abs_deviation_bps"] == 79.1235  # rounded


def test_format_json_extra_keys_merge():
    text = format_json([], extra={"chains": ["ethereum"], "lookback_minutes": 5})
    payload = json.loads(text)
    assert payload["chains"] == ["ethereum"]
    assert payload["lookback_minutes"] == 5
    assert payload["signal_count"] == 0


def test_signal_to_dict_drops_internal_samples_field():
    sig = _signal()
    sig.samples.append(object())  # type: ignore[arg-type]
    out = signal_to_dict(sig)
    assert "samples" not in out
