"""Build ChainStream queries that surface stablecoin trade prices.

We use the EVM ``DEXTrades`` cube (well-supported across Ethereum, Polygon,
BSC, Arbitrum) and read ``Trade.Buy.PriceInUSD`` / ``Trade.Sell.PriceInUSD``
relative to the stable's address. The ``Pairs`` cube is a more direct fit
where available, but its EVM schema isn't uniform across all 4 chains, so
DEXTrades is the conservative default.

If a future ChainStream release ships a stable ``Pairs`` cube with a uniform
schema, swap :func:`build_dextrades_query` for an analogous Pairs builder
without touching the detector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .chainstream import ChainStreamClient, ChainStreamError, GraphQLResponse
from .tokens import TokenSpec

# ChainStream EVM root maps logical chain names to its `network:` enum.
_CHAIN_ROOT: dict[str, str] = {
    "ethereum": "EVM(network: eth)",
    "polygon": "EVM(network: matic)",
    "bsc": "EVM(network: bsc)",
    "arbitrum": "EVM(network: arbitrum)",
}


def chain_root(chain: str) -> str:
    """Return ChainStream's GraphQL root selector for a supported EVM chain."""
    try:
        return _CHAIN_ROOT[chain.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported EVM chain: {chain}") from exc


def iso_minutes_ago(minutes: int, *, now: datetime | None = None) -> str:
    """Return the ISO-8601 timestamp ``minutes`` ago in UTC, second-precision.

    Pulled into a helper so tests can inject ``now`` deterministically.
    """
    base = now or datetime.now(tz=timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (base - timedelta(minutes=int(minutes))).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(slots=True)
class TradeObservation:
    """One DEX trade quote for a stable token, expressed in USD."""

    chain: str
    address: str
    symbol: str
    price_usd: float
    block_time: str  # ISO-8601 string
    tx_hash: str = ""


def build_dextrades_query(*, addresses: Iterable[str], chain: str) -> str:
    """Build a GraphQL document that asks for recent DEXTrades for ``addresses``.

    The query selects 50 most recent trades per chain root where the stable
    appears as either the buy- or sell-side currency. We read PriceInUSD on
    whichever side the stable is, and downstream code derives the deviation.
    """
    root = chain_root(chain)
    # ChainStream's GraphQL `where` accepts `in: [...]` on string-typed fields
    # like SmartContract. We rely on stringified address list interpolation
    # because `variables` for nested filter shapes vary by ChainStream release.
    address_list = ", ".join(f'"{addr}"' for addr in addresses)
    return f"""
      query StableDepegDEXTrades($since: DateTime!, $limit: Int!) {{
        {root} {{
          DEXTrades(
            limit: {{ count: $limit }}
            orderBy: {{ descending: Block_Time }}
            where: {{
              Block: {{ Time: {{ since: $since }} }}
              Trade: {{
                Buy: {{ Currency: {{ SmartContract: {{ in: [{address_list}] }} }} }}
              }}
            }}
          ) {{
            Block {{ Time }}
            Transaction {{ Hash }}
            Trade {{
              Buy {{
                PriceInUSD
                Currency {{ SmartContract Symbol Decimals }}
              }}
              Sell {{
                PriceInUSD
                Currency {{ SmartContract Symbol Decimals }}
              }}
            }}
          }}
        }}
      }}
    """.strip()


def parse_dextrades_response(
    response: GraphQLResponse,
    *,
    chain: str,
    known: dict[str, TokenSpec],
) -> list[TradeObservation]:
    """Translate a raw GraphQL response into TradeObservation rows.

    Only rows whose buy-side currency is in ``known`` are kept. The function is
    forgiving about missing fields so a partial schema mismatch doesn't break
    the whole scan.
    """
    if not response.data:
        return []
    # ChainStream nests under a single root key; pick the first.
    first_value = next(iter(response.data.values()), None)
    if not isinstance(first_value, dict):
        return []
    rows = first_value.get("DEXTrades") or []
    out: list[TradeObservation] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        block = raw.get("Block") or {}
        tx = raw.get("Transaction") or {}
        trade = raw.get("Trade") or {}
        buy = trade.get("Buy") or {}
        currency = buy.get("Currency") or {}
        addr = str(currency.get("SmartContract") or "").lower()
        if not addr:
            continue
        spec = known.get(addr)
        if not spec:
            continue
        try:
            price = float(buy.get("PriceInUSD") or 0.0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        out.append(
            TradeObservation(
                chain=chain,
                address=addr,
                symbol=spec.symbol,
                price_usd=price,
                block_time=str(block.get("Time") or ""),
                tx_hash=str(tx.get("Hash") or ""),
            )
        )
    return out


def fetch_trades(
    client: ChainStreamClient,
    *,
    chain: str,
    tokens: list[TokenSpec],
    lookback_minutes: int,
    limit: int = 50,
) -> tuple[list[TradeObservation], dict[str, Any]]:
    """Fetch and parse recent DEX trades for ``tokens`` on ``chain``.

    Returns ``(observations, extensions)`` so the caller can log credits etc.
    Raises :class:`ChainStreamError` on transport / GraphQL failure.
    """
    if not tokens:
        return [], {}
    addresses = [tok.address for tok in tokens]
    known = {tok.address: tok for tok in tokens}
    since = iso_minutes_ago(lookback_minutes)
    query = build_dextrades_query(addresses=addresses, chain=chain)
    try:
        response = client.query(query, variables={"since": since, "limit": int(limit)})
    except ChainStreamError:
        raise
    return parse_dextrades_response(response, chain=chain, known=known), response.extensions
