"""Tests for detector aggregation + classification."""

from __future__ import annotations

import pytest

from stable_depeg_radar.detector import DepegSignal, Observation, detect_depegs


def _obs(price: float, *, address="0xabc", chain="ethereum", symbol="TEST"):
    return Observation(chain, address, symbol, price, "2026-05-02T00:00:00Z")


def test_below_info_threshold_emits_no_signal():
    # 1.0001 = +1bp; default info threshold is 25 bps.
    signals = detect_depegs([_obs(1.0001), _obs(1.0002)])
    assert signals == []


def test_info_tier_threshold_inclusive_boundary_does_not_fire():
    # exactly 25 bps at info threshold => not strictly greater => no signal
    signals = detect_depegs([_obs(1.0025), _obs(1.0025)])
    assert signals == []


def test_info_tier_just_above_threshold_fires_info():
    signals = detect_depegs([_obs(1.0026), _obs(1.0026)])
    assert len(signals) == 1
    assert signals[0].severity == "info"


def test_warning_tier_classification():
    # ~150 bps drop
    signals = detect_depegs([_obs(0.985), _obs(0.985)])
    assert len(signals) == 1
    assert signals[0].severity == "warning"
    assert signals[0].deviation_bps == pytest.approx(-150.0, rel=1e-6)


def test_critical_tier_classification():
    # 5% drop = 500 bps
    signals = detect_depegs([_obs(0.95), _obs(0.95)])
    assert len(signals) == 1
    assert signals[0].severity == "critical"


def test_signed_deviation_above_one():
    signals = detect_depegs([_obs(1.05), _obs(1.05)])
    assert signals[0].deviation_bps > 0
    assert signals[0].severity == "critical"


def test_uses_median_price_to_resist_outliers():
    # Three samples: 0.999, 1.000, 1.998 — mean would scream depeg, median is 1.000
    signals = detect_depegs(
        [
            _obs(0.999),
            _obs(1.000),
            _obs(1.998),
        ]
    )
    assert signals == []


def test_groups_by_chain_and_address(stable_observations):
    signals = detect_depegs(stable_observations)
    # USDT samples are sub-threshold; USDC ~ -30 bps (info); USDe ~ -500 bps (critical)
    by_token = {s.token: s for s in signals}
    assert "USDT" not in by_token
    assert by_token["USDC"].severity == "info"
    assert by_token["USDe"].severity == "critical"


def test_signals_sorted_by_abs_deviation_desc(stable_observations):
    signals = detect_depegs(stable_observations)
    devs = [s.abs_deviation_bps for s in signals]
    assert devs == sorted(devs, reverse=True)


def test_drops_non_positive_prices():
    signals = detect_depegs(
        [
            _obs(0.0),
            _obs(-1.0),
            _obs(0.95),
            _obs(0.95),
        ]
    )
    assert len(signals) == 1
    # only the two valid samples informed the signal
    assert signals[0].sample_count == 2


def test_block_time_range_min_max():
    obs = [
        Observation("ethereum", "0xabc", "X", 0.95, "2026-05-02T00:01:00Z"),
        Observation("ethereum", "0xabc", "X", 0.95, "2026-05-02T00:00:00Z"),
        Observation("ethereum", "0xabc", "X", 0.95, "2026-05-02T00:02:00Z"),
    ]
    signals = detect_depegs(obs)
    assert signals[0].block_time_range == (
        "2026-05-02T00:00:00Z",
        "2026-05-02T00:02:00Z",
    )


def test_invalid_thresholds_raise():
    with pytest.raises(ValueError):
        detect_depegs([_obs(0.95)], info_bps=0)
    with pytest.raises(ValueError):
        detect_depegs([_obs(0.95)], info_bps=200, warn_bps=100)
    with pytest.raises(ValueError):
        detect_depegs([_obs(0.95)], info_bps=10, warn_bps=20, crit_bps=15)


def test_chain_grouping_normalises_case():
    obs = [
        Observation("Ethereum", "0xABC", "X", 0.95),
        Observation("ETHEREUM", "0xabc", "X", 0.95),
    ]
    signals = detect_depegs(obs)
    assert len(signals) == 1
    assert signals[0].sample_count == 2


def test_depeg_signal_dataclass_helpers():
    sig = DepegSignal(
        chain="ethereum",
        token="USDC",
        address="0xa0b8",
        observed_price_usd=0.99,
        deviation_bps=-100.0,
        sample_count=3,
        block_time_range=("a", "b"),
        severity="warning",
    )
    assert sig.abs_deviation_bps == 100.0
