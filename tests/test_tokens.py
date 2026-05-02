"""Tests for the built-in stable token registry."""

from __future__ import annotations

import pytest

from stable_depeg_radar.tokens import (
    KNOWN_STABLES,
    KNOWN_SYMBOLS,
    SUPPORTED_CHAINS,
    filter_by_symbols,
    lookup_token,
    tokens_for_chain,
)


def test_supported_chains_are_exactly_the_four_evm_chains():
    assert SUPPORTED_CHAINS == ("ethereum", "polygon", "bsc", "arbitrum")


def test_every_known_stable_address_is_lowercase():
    for chain, table in KNOWN_STABLES.items():
        for addr, spec in table.items():
            assert addr == addr.lower(), f"{chain}/{addr} not lowercase"
            assert spec.address == addr


def test_known_symbols_includes_all_six_top_stables():
    expected = {"USDT", "USDC", "DAI", "FRAX", "USDe", "USDS"}
    assert expected.issubset(set(KNOWN_SYMBOLS))


def test_lookup_token_is_case_insensitive_on_address(usdt_eth_address):
    upper = usdt_eth_address.upper()
    spec_lower = lookup_token("ethereum", usdt_eth_address)
    spec_upper = lookup_token("ethereum", upper)
    assert spec_lower is not None
    assert spec_upper is not None
    assert spec_lower == spec_upper
    assert spec_lower.symbol == "USDT"
    assert spec_lower.decimals == 6


def test_lookup_token_is_case_insensitive_on_chain(usdc_eth_address):
    spec = lookup_token("ETHEREUM", usdc_eth_address)
    assert spec is not None
    assert spec.symbol == "USDC"


def test_lookup_token_returns_none_for_unknown_chain(usdt_eth_address):
    assert lookup_token("solana", usdt_eth_address) is None


def test_lookup_token_returns_none_for_unknown_address():
    assert lookup_token("ethereum", "0x" + "00" * 20) is None


def test_lookup_token_returns_none_on_empty_inputs():
    assert lookup_token("", "0xabc") is None
    assert lookup_token("ethereum", "") is None


def test_tokens_for_chain_returns_empty_for_unknown():
    assert tokens_for_chain("nope") == ()


def test_tokens_for_chain_returns_all_eth_stables():
    tokens = tokens_for_chain("ethereum")
    symbols = {t.symbol for t in tokens}
    assert {"USDT", "USDC", "DAI", "FRAX", "USDe", "USDS"}.issubset(symbols)


def test_filter_by_symbols_none_returns_all():
    full = tokens_for_chain("ethereum")
    assert filter_by_symbols("ethereum", None) == full
    assert filter_by_symbols("ethereum", []) == full


def test_filter_by_symbols_subsets_correctly():
    tokens = filter_by_symbols("ethereum", ["USDT", "DAI"])
    symbols = {t.symbol for t in tokens}
    assert symbols == {"USDT", "DAI"}


def test_filter_by_symbols_is_case_insensitive():
    upper = filter_by_symbols("ethereum", ["usdt"])
    assert len(upper) == 1
    assert upper[0].symbol == "USDT"


@pytest.mark.parametrize(
    "chain,symbol",
    [
        ("ethereum", "USDT"),
        ("polygon", "USDC"),
        ("bsc", "USDT"),
        ("arbitrum", "USDC"),
        ("arbitrum", "FRAX"),
    ],
)
def test_each_listed_chain_has_at_least_one_canonical_stable(chain, symbol):
    tokens = tokens_for_chain(chain)
    symbols = {t.symbol for t in tokens}
    assert symbol in symbols
