"""Optional Claude-powered reasoning for depeg signals.

This module is *optional*: it only matters when the user passes ``--reasoning``.
We import :mod:`anthropic` lazily so the base install (no extras) stays free of
network deps. When the SDK isn't installed the function returns the original
signals unchanged with a clear hint in the per-signal ``reasoning`` field.
"""

from __future__ import annotations

import os
from typing import Iterable

from .detector import DepegSignal

# Default model. Override via ANTHROPIC_MODEL env var; current latest stable
# series at the time of writing is the Claude 4 family.
DEFAULT_MODEL = "claude-opus-4-5"

_DISABLED_HINT = (
    "Claude reasoning unavailable: install the optional extra "
    "(`pip install 'stable-depeg-radar[ai-reasoning]'`) and set ANTHROPIC_API_KEY."
)


def _format_signal_for_prompt(sig: DepegSignal) -> str:
    side = "above" if sig.deviation_bps > 0 else "below"
    return (
        f"- chain={sig.chain} token={sig.token} address={sig.address} "
        f"observed_price=${sig.observed_price_usd:.6f} "
        f"deviation={abs(sig.deviation_bps):.1f} bps {side} $1 "
        f"samples={sig.sample_count} severity={sig.severity}"
    )


def _build_prompt(signals: list[DepegSignal]) -> str:
    body = "\n".join(_format_signal_for_prompt(s) for s in signals)
    return (
        "You are a stablecoin risk analyst. Given the following depeg "
        "signals harvested from on-chain DEX trades, write one short sentence "
        "(<= 30 words) per signal explaining (a) the most plausible cause and "
        "(b) what to watch next. Return one line per signal in the order given, "
        "prefixed with the token symbol and a colon. No preamble.\n\n"
        f"Signals:\n{body}\n"
    )


def annotate_with_reasoning(
    signals: list[DepegSignal],
    *,
    api_key: str | None = None,
    model: str | None = None,
    client: object | None = None,
) -> list[DepegSignal]:
    """Attach a one-line Claude rationale to each signal in place.

    Parameters
    ----------
    signals:
        Output of :func:`detector.detect_depegs`.
    api_key:
        Defaults to ``ANTHROPIC_API_KEY`` env. When missing, every signal gets
        a hint string instead of a real explanation, and the function returns
        successfully (no exception).
    model:
        Override the model. Defaults to ``ANTHROPIC_MODEL`` env or
        :data:`DEFAULT_MODEL`.
    client:
        Inject a pre-built ``anthropic.Anthropic`` (or compatible) client for
        testing.
    """
    if not signals:
        return signals

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key and client is None:
        for sig in signals:
            sig.reasoning = _DISABLED_HINT
        return signals

    if client is None:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError:
            for sig in signals:
                sig.reasoning = _DISABLED_HINT
            return signals
        client = anthropic.Anthropic(api_key=key)

    chosen_model = (
        model or os.environ.get("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL
    )
    prompt = _build_prompt(signals)
    try:
        response = client.messages.create(  # type: ignore[attr-defined]
            model=chosen_model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # pragma: no cover - network path
        for sig in signals:
            sig.reasoning = f"Claude reasoning failed: {exc}"
        return signals

    text = _extract_text(response)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # Pair lines back with signals by index. If Claude returned fewer lines,
    # leave the tail un-annotated rather than mis-aligning.
    for sig, line in zip(signals, lines):
        sig.reasoning = line
    return signals


def _extract_text(response: object) -> str:
    """Best-effort extraction of text from an anthropic.Message-like object."""
    content = getattr(response, "content", None)
    if not content:
        return ""
    chunks: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunks)


def iter_reasoned_signals(
    signals: Iterable[DepegSignal],
) -> Iterable[tuple[DepegSignal, str]]:
    """Yield (signal, rationale_or_empty) — convenient for formatters."""
    for sig in signals:
        yield sig, sig.reasoning or ""
