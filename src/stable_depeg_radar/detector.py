"""Depeg detection: aggregate per (chain, token) trade observations into signals.

A *signal* is the per-(chain, token) summary over the lookback window. The
deviation is computed from the **median** observed price (more robust than the
mean against a single outlier print) and reported in basis points (1 bp =
0.01%, so 25 bps = 0.25%).

Severity tiers (defaults; tunable via thresholds):
    info     -> |dev_bps| > 25   (0.25%)
    warning  -> |dev_bps| > 100  (1.00%)
    critical -> |dev_bps| > 300  (3.00%)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Iterable, Literal

Severity = Literal["info", "warning", "critical"]


@dataclass(slots=True)
class Observation:
    """One (chain, token, price) sample at a point in time.

    Decoupled from :class:`pairs.TradeObservation` so detection logic can be
    fed by other sources (e.g. a static fixture in tests, or a future Pairs
    cube reader).
    """

    chain: str
    address: str
    token: str  # symbol
    price_usd: float
    block_time: str = ""


@dataclass(slots=True)
class DepegSignal:
    """Aggregated depeg result for a single (chain, token) pair."""

    chain: str
    token: str
    address: str
    observed_price_usd: float
    deviation_bps: float  # signed: positive = above $1, negative = below
    sample_count: int
    block_time_range: tuple[str, str]
    severity: Severity
    reasoning: str | None = None
    samples: list[Observation] = field(default_factory=list, repr=False)

    @property
    def abs_deviation_bps(self) -> float:
        return abs(self.deviation_bps)


def _bps_from_price(price_usd: float) -> float:
    """Convert a USD-denominated price to deviation from $1 in bps."""
    return (price_usd - 1.0) * 10_000.0


def _classify(abs_bps: float, *, info: float, warn: float, crit: float) -> Severity | None:
    """Return the severity bucket, or ``None`` if below the info threshold."""
    if abs_bps > crit:
        return "critical"
    if abs_bps > warn:
        return "warning"
    if abs_bps > info:
        return "info"
    return None


def _time_range(samples: list[Observation]) -> tuple[str, str]:
    times = [s.block_time for s in samples if s.block_time]
    if not times:
        return ("", "")
    return (min(times), max(times))


def detect_depegs(
    observations: Iterable[Observation],
    *,
    info_bps: float = 25.0,
    warn_bps: float = 100.0,
    crit_bps: float = 300.0,
) -> list[DepegSignal]:
    """Group observations by (chain, address) and emit signals above ``info_bps``.

    Validation:
        - thresholds must satisfy ``0 < info_bps <= warn_bps <= crit_bps``
        - non-positive prices are dropped silently
        - groups with no surviving samples produce no signal

    The output is sorted by absolute deviation, descending — most severe first.
    """
    if not (info_bps > 0 and warn_bps >= info_bps and crit_bps >= warn_bps):
        raise ValueError(
            "thresholds must satisfy 0 < info_bps <= warn_bps <= crit_bps"
        )

    grouped: dict[tuple[str, str], list[Observation]] = {}
    for obs in observations:
        if obs.price_usd <= 0:
            continue
        key = (obs.chain.strip().lower(), obs.address.strip().lower())
        grouped.setdefault(key, []).append(obs)

    signals: list[DepegSignal] = []
    for (chain, address), samples in grouped.items():
        if not samples:
            continue
        prices = [s.price_usd for s in samples]
        med_price = float(median(prices))
        dev_bps = _bps_from_price(med_price)
        severity = _classify(
            abs(dev_bps), info=info_bps, warn=warn_bps, crit=crit_bps
        )
        if severity is None:
            continue
        signals.append(
            DepegSignal(
                chain=chain,
                token=samples[0].token,
                address=address,
                observed_price_usd=med_price,
                deviation_bps=dev_bps,
                sample_count=len(samples),
                block_time_range=_time_range(samples),
                severity=severity,
                samples=list(samples),
            )
        )

    signals.sort(key=lambda s: s.abs_deviation_bps, reverse=True)
    return signals
