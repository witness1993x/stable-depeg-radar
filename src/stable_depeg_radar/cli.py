"""Console entrypoint for ``stable-radar``.

Subcommands:
    scan      poll ChainStream once and report any depegs.

Exit codes:
    0  success (regardless of whether any signals fired)
    1  scan / network error
    2  bad CLI arguments
    3  missing required environment (e.g. ``CHAINSTREAM_API_KEY``)
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

from . import __version__
from .chainstream import DEFAULT_ENDPOINT, ChainStreamClient, ChainStreamError
from .detector import Observation, detect_depegs
from .format import format_json, format_pretty
from .pairs import fetch_trades
from .reasoning import annotate_with_reasoning
from .tokens import SUPPORTED_CHAINS, KNOWN_SYMBOLS, filter_by_symbols

EXIT_OK = 0
EXIT_SCAN_ERROR = 1
EXIT_BAD_ARGS = 2
EXIT_MISSING_KEY = 3


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stable-radar",
        description=(
            "Stablecoin depeg early-warning radar. Polls ChainStream for recent "
            "DEX prices of USDT/USDC/DAI/FRAX/USDe/USDS across major EVM chains "
            "and emits an alert when prices drift from $1 by more than the "
            "configured basis-point threshold."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"stable-radar {__version__}",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    scan = sub.add_parser(
        "scan",
        help="Run a single polling pass and print any depeg signals.",
    )
    scan.add_argument(
        "--chains",
        type=_csv,
        default=list(SUPPORTED_CHAINS),
        help=(
            "Comma-separated chains to scan. "
            f"Default: {','.join(SUPPORTED_CHAINS)}."
        ),
    )
    scan.add_argument(
        "--tokens",
        type=_csv,
        default=list(KNOWN_SYMBOLS),
        help=(
            "Comma-separated token symbols to monitor. "
            f"Default: {','.join(KNOWN_SYMBOLS)}."
        ),
    )
    scan.add_argument(
        "--lookback-minutes",
        type=int,
        default=15,
        help="Lookback window in minutes (default: 15).",
    )
    scan.add_argument(
        "--threshold-bps",
        type=float,
        default=25.0,
        help="info-tier deviation threshold in basis points (default: 25).",
    )
    scan.add_argument(
        "--warn-bps",
        type=float,
        default=100.0,
        help="warning-tier threshold in basis points (default: 100).",
    )
    scan.add_argument(
        "--crit-bps",
        type=float,
        default=300.0,
        help="critical-tier threshold in basis points (default: 300).",
    )
    scan.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Per-chain DEXTrades query limit (default: 50).",
    )
    scan.add_argument(
        "--reasoning",
        action="store_true",
        help="Annotate each signal with a one-line Claude-generated rationale.",
    )
    scan.add_argument(
        "--endpoint",
        default=os.environ.get("CHAINSTREAM_ENDPOINT", DEFAULT_ENDPOINT),
        help=(
            "ChainStream GraphQL endpoint. Falls back to "
            "$CHAINSTREAM_ENDPOINT then the public default."
        ),
    )
    out = scan.add_mutually_exclusive_group()
    out.add_argument("--json", action="store_true", help="Emit JSON instead of pretty text.")
    out.add_argument("--pretty", action="store_true", help="Force pretty output (default).")
    scan.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in pretty output.",
    )
    return parser


def _validate_chains(chains: list[str]) -> list[str]:
    bad = [c for c in chains if c.strip().lower() not in SUPPORTED_CHAINS]
    if bad:
        raise SystemExit(
            f"unsupported chain(s): {', '.join(bad)}. "
            f"Choose from: {', '.join(SUPPORTED_CHAINS)}"
        )
    return [c.strip().lower() for c in chains]


def _validate_thresholds(info_bps: float, warn_bps: float, crit_bps: float) -> None:
    if not (info_bps > 0 and warn_bps >= info_bps and crit_bps >= warn_bps):
        raise SystemExit(
            "--threshold-bps, --warn-bps, --crit-bps must satisfy "
            "0 < threshold-bps <= warn-bps <= crit-bps"
        )


def run_scan(args: argparse.Namespace) -> int:
    api_key = os.environ.get("CHAINSTREAM_API_KEY", "").strip()
    if not api_key:
        print("error: CHAINSTREAM_API_KEY env var is required", file=sys.stderr)
        return EXIT_MISSING_KEY

    try:
        chains = _validate_chains(args.chains)
        _validate_thresholds(args.threshold_bps, args.warn_bps, args.crit_bps)
    except SystemExit as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_BAD_ARGS

    client = ChainStreamClient(endpoint=args.endpoint, api_key=api_key)

    observations: list[Observation] = []
    for chain in chains:
        tokens = filter_by_symbols(chain, args.tokens)
        if not tokens:
            continue
        try:
            trades, _ext = fetch_trades(
                client,
                chain=chain,
                tokens=list(tokens),
                lookback_minutes=args.lookback_minutes,
                limit=args.limit,
            )
        except ChainStreamError as exc:
            print(f"error: ChainStream scan failed on {chain}: {exc}", file=sys.stderr)
            return EXIT_SCAN_ERROR
        for trade in trades:
            observations.append(
                Observation(
                    chain=trade.chain,
                    address=trade.address,
                    token=trade.symbol,
                    price_usd=trade.price_usd,
                    block_time=trade.block_time,
                )
            )

    signals = detect_depegs(
        observations,
        info_bps=args.threshold_bps,
        warn_bps=args.warn_bps,
        crit_bps=args.crit_bps,
    )

    if args.reasoning:
        annotate_with_reasoning(signals)

    if args.json:
        print(
            format_json(
                signals,
                extra={
                    "chains": chains,
                    "tokens": args.tokens,
                    "lookback_minutes": args.lookback_minutes,
                    "thresholds_bps": {
                        "info": args.threshold_bps,
                        "warning": args.warn_bps,
                        "critical": args.crit_bps,
                    },
                },
            )
        )
    else:
        use_color = (not args.no_color) and sys.stdout.isatty()
        header = (
            f"stable-radar scan: chains={','.join(chains)} "
            f"lookback={args.lookback_minutes}m threshold={args.threshold_bps}bps"
        )
        print(format_pretty(signals, color=use_color, header=header))
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        return run_scan(args)
    parser.print_help()
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
