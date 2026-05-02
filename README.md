# stable-depeg-radar

[![CI](https://github.com/witness1993x/stable-depeg-radar/actions/workflows/ci.yml/badge.svg)](https://github.com/witness1993x/stable-depeg-radar/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/witness1993x/stable-depeg-radar)](./LICENSE)
[![Stars](https://img.shields.io/github/stars/witness1993x/stable-depeg-radar?style=social)](https://github.com/witness1993x/stable-depeg-radar/stargazers)
[![Issues](https://img.shields.io/github/issues/witness1993x/stable-depeg-radar)](https://github.com/witness1993x/stable-depeg-radar/issues)
[![Last commit](https://img.shields.io/github/last-commit/witness1993x/stable-depeg-radar/main)](https://github.com/witness1993x/stable-depeg-radar/commits/main)

> Multichain stablecoin depeg early-warning radar powered by **ChainStream** GraphQL, with optional **Claude AI** reasoning.

`stable-depeg-radar` polls the ChainStream `DEXTrades` cube on **Ethereum, Polygon, BSC, and Arbitrum**, reads recent USD prices for the major stables (`USDT`, `USDC`, `DAI`, `FRAX`, `USDe`, `USDS`) and raises an alert whenever the median trade price drifts from `$1` by more than a configurable basis-point threshold. Severity tiers are tuned to surface real depeg-style events (USDC/SVB-2023, UST/Terra-2022) rather than DEX micro-noise.

This repo is the third in a series of ChainStream-backed radars and is the **Python** entry — complementing the two TypeScript siblings:

| Repo | Cube | Focus |
|---|---|---|
| [`chainstream-launch-radar`](https://github.com/witness1993x/chainstream-launch-radar) | Solana `DEXTrades` | new memecoin launches |
| [`whale-pulse-evm`](https://github.com/witness1993x/whale-pulse-evm) | EVM `Transfers` | large transfers / whale wallets |
| **`stable-depeg-radar`** *(this repo)* | EVM `DEXTrades` | stablecoin price deviation from $1 |

## Differentiation

- **What we monitor**: the *price* of an asset, not its launch event (`launch-radar`) or its transfer flow (`whale-pulse`). Depeg is a different alpha surface — it cares about a few-bps drift on a single token, not throughput.
- **Severity model**: deviation in basis points (bps), bucketed `info / warning / critical` so dashboards can route the firehose vs. the page-an-engineer events differently.
- **Pure stdlib runtime**: no `requests`, no `aiohttp`. The GraphQL client is built on `urllib.request` so a `pip install stable-depeg-radar` installs *zero* third-party packages by default.

## Install

```bash
pip install stable-depeg-radar               # core (no extras)
pip install "stable-depeg-radar[ai-reasoning]"  # adds anthropic for --reasoning
```

Local / dev install:

```bash
git clone https://github.com/witness1993x/stable-depeg-radar
cd stable-depeg-radar
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

## Configure

Required:

```bash
export CHAINSTREAM_API_KEY=cs_live_...
```

Optional:

```bash
export CHAINSTREAM_ENDPOINT=https://graphql.chainstream.io/graphql  # default
export ANTHROPIC_API_KEY=sk-ant-...   # only needed for --reasoning
export ANTHROPIC_MODEL=claude-opus-4-5
```

A copyable `.env.example` is included.

## Usage

```bash
# Scan all chains, all tokens, 15-minute lookback, info threshold 25 bps.
stable-radar scan

# Tighten the lookback window to 5 minutes and scan only Ethereum + Arbitrum.
stable-radar scan --chains ethereum,arbitrum --lookback-minutes 5

# Watch only USDC / USDe with a 50-bps info threshold and emit JSON.
stable-radar scan --tokens USDC,USDe --threshold-bps 50 --json

# Add a one-line Claude rationale per signal.
stable-radar scan --reasoning
```

### Sample output

Pretty:

```
stable-radar scan: chains=ethereum,polygon,bsc,arbitrum lookback=15m threshold=25bps
detected 2 depeg signal(s) (sorted by severity):
  [WARN] USDe   $0.992100  v   79.0 bps  chain=ethereum samples=18 addr=0x4c9edd...
  [INFO] USDT   $1.000300  ^    3.0 bps  chain=bsc      samples=12 addr=0x55d398...
```

JSON (excerpt):

```json
{
  "schema": "stable-depeg-radar/v1",
  "signal_count": 2,
  "signals": [
    {
      "chain": "ethereum",
      "token": "USDe",
      "address": "0x4c9edd5852cd905f086c759e8383e09bff1e68b3",
      "observed_price_usd": 0.9921,
      "deviation_bps": -79.0,
      "abs_deviation_bps": 79.0,
      "sample_count": 18,
      "block_time_range": ["2026-05-02T05:42:11Z", "2026-05-02T05:57:48Z"],
      "severity": "warning",
      "reasoning": null
    }
  ]
}
```

## Severity tiers

| Tier | Default threshold | Meaning |
|---|---|---|
| `info` | `\|deviation\| > 25 bps` (0.25%) | worth logging, often DEX noise |
| `warning` | `\|deviation\| > 100 bps` (1.00%) | sustained drift; check liquidity |
| `critical` | `\|deviation\| > 300 bps` (3.00%) | depeg-class event; page an operator |

All three tiers are tunable via `--threshold-bps`, `--warn-bps`, `--crit-bps`.

## Architecture

```
stable_depeg_radar/
  chainstream.py   # stdlib GraphQL POST (X-API-KEY) — no requests
  pairs.py         # build EVM DEXTrades query + parse trade rows
  tokens.py        # built-in stable contract registry per chain
  detector.py      # group trades, compute median, classify severity
  reasoning.py     # optional Claude annotation (lazy anthropic import)
  format.py        # pretty + JSON
  cli.py           # argparse + console_script `stable-radar`
```

`tokens.py` ships a curated registry of stable contracts (lowercase address + decimals + symbol) so the user doesn't have to look them up. Adding a new stable means appending one row to that file plus a test.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | success — scan completed (signals may or may not have fired) |
| `1` | scan or network error |
| `2` | bad CLI arguments |
| `3` | missing required env var (`CHAINSTREAM_API_KEY`) |

## License

[MIT](./LICENSE) — see file for full text.
