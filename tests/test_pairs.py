"""Tests for the DEXTrades query builder + response parser."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stable_depeg_radar.chainstream import GraphQLResponse
from stable_depeg_radar.pairs import (
    build_dextrades_query,
    chain_root,
    iso_minutes_ago,
    parse_dextrades_response,
)
from stable_depeg_radar.tokens import lookup_token


def test_chain_root_known():
    assert chain_root("ethereum") == "EVM(network: eth)"
    assert chain_root("polygon") == "EVM(network: matic)"
    assert chain_root("BSC") == "EVM(network: bsc)"
    assert chain_root("arbitrum") == "EVM(network: arbitrum)"


def test_chain_root_unknown_raises():
    with pytest.raises(ValueError):
        chain_root("solana")


def test_iso_minutes_ago_is_deterministic():
    fixed = datetime(2026, 5, 2, 6, 0, 0, tzinfo=timezone.utc)
    assert iso_minutes_ago(15, now=fixed) == "2026-05-02T05:45:00Z"


def test_iso_minutes_ago_handles_naive_datetime():
    fixed = datetime(2026, 5, 2, 6, 0, 0)  # no tzinfo
    out = iso_minutes_ago(5, now=fixed)
    assert out == "2026-05-02T05:55:00Z"


def test_build_dextrades_query_embeds_addresses_and_chain_root():
    query = build_dextrades_query(
        addresses=["0xabc", "0xdef"],
        chain="ethereum",
    )
    assert "EVM(network: eth)" in query
    assert "0xabc" in query and "0xdef" in query
    # both variables we pass at execution time:
    assert "$since" in query and "$limit" in query


def test_parse_dextrades_response_keeps_only_known_addresses(usdt_eth_address):
    spec = lookup_token("ethereum", usdt_eth_address)
    assert spec is not None
    payload = {
        "EVM": {
            "DEXTrades": [
                {
                    "Block": {"Time": "2026-05-02T05:50:00Z"},
                    "Transaction": {"Hash": "0xtx1"},
                    "Trade": {
                        "Buy": {
                            "PriceInUSD": 0.998,
                            "Currency": {
                                "SmartContract": usdt_eth_address.upper(),
                                "Symbol": "USDT",
                                "Decimals": 6,
                            },
                        },
                        "Sell": {
                            "PriceInUSD": 1.0,
                            "Currency": {"SmartContract": "0xother"},
                        },
                    },
                },
                {
                    # Unknown stable address — must be filtered out.
                    "Block": {"Time": "2026-05-02T05:51:00Z"},
                    "Transaction": {"Hash": "0xtx2"},
                    "Trade": {
                        "Buy": {
                            "PriceInUSD": 0.99,
                            "Currency": {"SmartContract": "0xunknown"},
                        }
                    },
                },
            ]
        }
    }
    response = GraphQLResponse(data=payload, errors=[], extensions={})
    rows = parse_dextrades_response(
        response,
        chain="ethereum",
        known={usdt_eth_address: spec},
    )
    assert len(rows) == 1
    assert rows[0].symbol == "USDT"
    assert rows[0].address == usdt_eth_address
    assert rows[0].price_usd == 0.998
    assert rows[0].chain == "ethereum"
    assert rows[0].block_time == "2026-05-02T05:50:00Z"


def test_parse_dextrades_response_drops_zero_or_missing_prices(usdc_eth_address):
    spec = lookup_token("ethereum", usdc_eth_address)
    assert spec is not None
    payload = {
        "EVM": {
            "DEXTrades": [
                {
                    "Block": {"Time": "t1"},
                    "Trade": {
                        "Buy": {
                            "PriceInUSD": 0,
                            "Currency": {"SmartContract": usdc_eth_address},
                        }
                    },
                },
                {
                    "Block": {"Time": "t2"},
                    "Trade": {
                        "Buy": {
                            "PriceInUSD": None,
                            "Currency": {"SmartContract": usdc_eth_address},
                        }
                    },
                },
            ]
        }
    }
    response = GraphQLResponse(data=payload, errors=[], extensions={})
    rows = parse_dextrades_response(
        response, chain="ethereum", known={usdc_eth_address: spec}
    )
    assert rows == []


def test_parse_dextrades_response_handles_empty_data():
    response = GraphQLResponse(data={}, errors=[], extensions={})
    assert parse_dextrades_response(response, chain="ethereum", known={}) == []
