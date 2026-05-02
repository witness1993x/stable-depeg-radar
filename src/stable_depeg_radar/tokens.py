"""Built-in registry of stablecoin contracts on supported EVM chains.

Addresses are stored lowercase (0x-prefixed). Lookup is case-insensitive on the
input address. Decimals matter for converting raw on-chain amounts back to a USD
estimate when a price feed is unavailable.

Coverage rationale:
    - USDT/USDC/DAI: the three dominant fiat-backed pegs across all four chains.
    - FRAX: hybrid algorithmic peg, history of brief depegs.
    - USDe: Ethena's synthetic dollar — useful canary for funding-rate stress.
    - USDS: Sky/Maker rebrand of DAI, watched for migration risk.
"""

from __future__ import annotations

from dataclasses import dataclass

# Supported chains. The set is closed because each chain needs its own
# ChainStream `EVM(network: ...)` root and its own price-source assumptions.
SUPPORTED_CHAINS: tuple[str, ...] = ("ethereum", "polygon", "bsc", "arbitrum")


@dataclass(frozen=True, slots=True)
class TokenSpec:
    """Static metadata about a stablecoin on a given chain."""

    chain: str
    symbol: str
    address: str  # lowercase 0x-prefixed
    decimals: int
    description: str = ""


# NOTE: keep addresses lowercase. lookup_token normalises the input.
KNOWN_STABLES: dict[str, dict[str, TokenSpec]] = {
    "ethereum": {
        "0xdac17f958d2ee523a2206206994597c13d831ec7": TokenSpec(
            "ethereum",
            "USDT",
            "0xdac17f958d2ee523a2206206994597c13d831ec7",
            6,
            "Tether USD",
        ),
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": TokenSpec(
            "ethereum",
            "USDC",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            6,
            "USD Coin",
        ),
        "0x6b175474e89094c44da98b954eedeac495271d0f": TokenSpec(
            "ethereum",
            "DAI",
            "0x6b175474e89094c44da98b954eedeac495271d0f",
            18,
            "MakerDAO Dai",
        ),
        "0x853d955acef822db058eb8505911ed77f175b99e": TokenSpec(
            "ethereum",
            "FRAX",
            "0x853d955acef822db058eb8505911ed77f175b99e",
            18,
            "Frax",
        ),
        "0x4c9edd5852cd905f086c759e8383e09bff1e68b3": TokenSpec(
            "ethereum",
            "USDe",
            "0x4c9edd5852cd905f086c759e8383e09bff1e68b3",
            18,
            "Ethena USDe",
        ),
        "0xdc035d45d973e3ec169d2276ddab16f1e407384f": TokenSpec(
            "ethereum",
            "USDS",
            "0xdc035d45d973e3ec169d2276ddab16f1e407384f",
            18,
            "Sky USDS",
        ),
    },
    "polygon": {
        "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": TokenSpec(
            "polygon",
            "USDT",
            "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",
            6,
            "Tether USD (PoS)",
        ),
        "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": TokenSpec(
            "polygon",
            "USDC",
            "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
            6,
            "USDC (native)",
        ),
        "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063": TokenSpec(
            "polygon",
            "DAI",
            "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063",
            18,
            "MakerDAO Dai (PoS)",
        ),
    },
    "bsc": {
        "0x55d398326f99059ff775485246999027b3197955": TokenSpec(
            "bsc",
            "USDT",
            "0x55d398326f99059ff775485246999027b3197955",
            18,
            "Tether USD (BSC)",
        ),
        "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": TokenSpec(
            "bsc",
            "USDC",
            "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
            18,
            "USD Coin (BSC)",
        ),
    },
    "arbitrum": {
        "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": TokenSpec(
            "arbitrum",
            "USDT",
            "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
            6,
            "Tether USD (Arbitrum)",
        ),
        "0xaf88d065e77c8cc2239327c5edb3a432268e5831": TokenSpec(
            "arbitrum",
            "USDC",
            "0xaf88d065e77c8cc2239327c5edb3a432268e5831",
            6,
            "USDC (native, Arbitrum)",
        ),
        "0x17fc002b466eec40dae837fc4be5c67993ddbd6f": TokenSpec(
            "arbitrum",
            "FRAX",
            "0x17fc002b466eec40dae837fc4be5c67993ddbd6f",
            18,
            "Frax (Arbitrum)",
        ),
    },
}


# Convenience: every symbol we know about (across any chain).
KNOWN_SYMBOLS: tuple[str, ...] = tuple(
    sorted({tok.symbol for chain in KNOWN_STABLES.values() for tok in chain.values()})
)


def lookup_token(chain: str, address: str) -> TokenSpec | None:
    """Look up a token by (chain, address). Address is normalised to lowercase.

    Returns ``None`` when chain is unknown or address is not in the registry.
    The function is intentionally side-effect-free so detector code can probe
    cheaply per row.
    """
    if not chain or not address:
        return None
    chain_key = chain.strip().lower()
    chain_table = KNOWN_STABLES.get(chain_key)
    if not chain_table:
        return None
    return chain_table.get(address.strip().lower())


def tokens_for_chain(chain: str) -> tuple[TokenSpec, ...]:
    """Return all known stables on a given chain (empty tuple if chain unknown)."""
    chain_table = KNOWN_STABLES.get(chain.strip().lower(), {})
    return tuple(chain_table.values())


def filter_by_symbols(
    chain: str, symbols: tuple[str, ...] | list[str] | None
) -> tuple[TokenSpec, ...]:
    """Return tokens on ``chain`` filtered to ``symbols`` (case-insensitive).

    ``None`` or empty selector returns the full chain set, which is the natural
    default when the user passes ``--tokens`` with no value.
    """
    chain_tokens = tokens_for_chain(chain)
    if not symbols:
        return chain_tokens
    wanted = {s.strip().upper() for s in symbols if s and s.strip()}
    if not wanted:
        return chain_tokens
    return tuple(tok for tok in chain_tokens if tok.symbol.upper() in wanted)
