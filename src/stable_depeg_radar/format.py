"""Output formatters: pretty (terminal) and JSON (machine).

The pretty formatter is intentionally lightweight (no third-party color libs).
ANSI codes are emitted only when the caller passes ``color=True``; the CLI
defaults to True when stdout is a TTY.
"""

from __future__ import annotations

import json
from typing import Iterable

from .detector import DepegSignal

# ANSI helpers — kept inline so we don't depend on `colorama` or `rich`.
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_RED = "\x1b[31m"
_CYAN = "\x1b[36m"

_SEVERITY_COLOR = {
    "info": _CYAN,
    "warning": _YELLOW,
    "critical": _RED,
}

_SEVERITY_LABEL = {
    "info": "INFO",
    "warning": "WARN",
    "critical": "CRIT",
}


def _maybe_color(text: str, code: str, *, color: bool) -> str:
    if not color:
        return text
    return f"{code}{text}{_RESET}"


def _direction_arrow(deviation_bps: float) -> str:
    return "v" if deviation_bps < 0 else "^"


def format_pretty(
    signals: Iterable[DepegSignal],
    *,
    color: bool = True,
    header: str | None = None,
) -> str:
    """Return a multi-line, human-friendly summary string.

    Empty input renders a clear "no depeg" line so the CLI always prints
    *something* (silence on a successful scan is a UX bug).
    """
    signals_list = list(signals)
    lines: list[str] = []
    if header:
        lines.append(_maybe_color(header, _BOLD, color=color))

    if not signals_list:
        lines.append(
            _maybe_color(
                "OK  no stablecoin depeg detected above threshold.",
                _GREEN,
                color=color,
            )
        )
        return "\n".join(lines)

    lines.append(
        _maybe_color(
            f"detected {len(signals_list)} depeg signal(s) (sorted by severity):",
            _BOLD,
            color=color,
        )
    )
    for sig in signals_list:
        sev_code = _SEVERITY_COLOR.get(sig.severity, _DIM)
        sev_label = _SEVERITY_LABEL.get(sig.severity, sig.severity.upper())
        sev = _maybe_color(f"[{sev_label}]", sev_code, color=color)
        token = _maybe_color(sig.token, _BOLD, color=color)
        arrow = _direction_arrow(sig.deviation_bps)
        deviation = f"{arrow}{abs(sig.deviation_bps):7.1f} bps"
        deviation_colored = _maybe_color(deviation, sev_code, color=color)
        price = f"${sig.observed_price_usd:.6f}"
        meta = _maybe_color(
            f"chain={sig.chain} samples={sig.sample_count} addr={sig.address}",
            _DIM,
            color=color,
        )
        lines.append(f"  {sev} {token:<6} {price}  {deviation_colored}  {meta}")
        if sig.reasoning:
            lines.append(f"        reasoning: {sig.reasoning}")
    return "\n".join(lines)


def signal_to_dict(sig: DepegSignal) -> dict:
    """Translate a DepegSignal to a JSON-safe dict (drops samples)."""
    return {
        "chain": sig.chain,
        "token": sig.token,
        "address": sig.address,
        "observed_price_usd": round(sig.observed_price_usd, 8),
        "deviation_bps": round(sig.deviation_bps, 4),
        "abs_deviation_bps": round(sig.abs_deviation_bps, 4),
        "sample_count": sig.sample_count,
        "block_time_range": list(sig.block_time_range),
        "severity": sig.severity,
        "reasoning": sig.reasoning,
    }


def format_json(
    signals: Iterable[DepegSignal],
    *,
    indent: int | None = 2,
    extra: dict | None = None,
) -> str:
    """Return a stable-shaped JSON document for downstream tooling."""
    payload = {
        "schema": "stable-depeg-radar/v1",
        "signal_count": 0,
        "signals": [],
    }
    sigs = list(signals)
    payload["signal_count"] = len(sigs)
    payload["signals"] = [signal_to_dict(s) for s in sigs]
    if extra:
        payload.update(extra)
    return json.dumps(payload, indent=indent, sort_keys=False)
