"""Tests for argparse wiring + CLI exit codes (no real network)."""

from __future__ import annotations

import json

import pytest

from stable_depeg_radar import cli
from stable_depeg_radar.cli import (
    EXIT_BAD_ARGS,
    EXIT_MISSING_KEY,
    EXIT_OK,
    build_parser,
    main,
)
from stable_depeg_radar.pairs import TradeObservation


def test_parser_help_does_not_crash(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    out = capsys.readouterr().out
    assert "stable-radar" in out


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "stable-radar" in out


def test_no_subcommand_prints_help(capsys):
    rc = main([])
    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_scan_default_chains_match_supported():
    parser = build_parser()
    args = parser.parse_args(["scan"])
    assert args.chains == ["ethereum", "polygon", "bsc", "arbitrum"]


def test_scan_overrides_chains_and_tokens():
    parser = build_parser()
    args = parser.parse_args(
        [
            "scan",
            "--chains",
            "ethereum,arbitrum",
            "--tokens",
            "USDC,USDe",
            "--lookback-minutes",
            "5",
        ]
    )
    assert args.chains == ["ethereum", "arbitrum"]
    assert args.tokens == ["USDC", "USDe"]
    assert args.lookback_minutes == 5


def test_scan_rejects_unknown_chain(monkeypatch, capsys):
    monkeypatch.setenv("CHAINSTREAM_API_KEY", "k")
    rc = main(["scan", "--chains", "solana"])
    assert rc == EXIT_BAD_ARGS
    err = capsys.readouterr().err
    assert "unsupported chain" in err.lower()


def test_scan_rejects_inverted_thresholds(monkeypatch, capsys):
    monkeypatch.setenv("CHAINSTREAM_API_KEY", "k")
    rc = main(["scan", "--threshold-bps", "200", "--warn-bps", "100"])
    assert rc == EXIT_BAD_ARGS
    err = capsys.readouterr().err
    assert "threshold" in err.lower()


def test_scan_missing_api_key_exit_3(monkeypatch, capsys):
    monkeypatch.delenv("CHAINSTREAM_API_KEY", raising=False)
    rc = main(["scan"])
    assert rc == EXIT_MISSING_KEY
    err = capsys.readouterr().err
    assert "CHAINSTREAM_API_KEY" in err


def test_scan_pretty_no_signals(monkeypatch, capsys, usde_eth_address):
    monkeypatch.setenv("CHAINSTREAM_API_KEY", "k")

    # Patch fetch_trades inside the cli module to avoid hitting the network.
    def fake_fetch(client, *, chain, tokens, lookback_minutes, limit):
        return [], {}

    monkeypatch.setattr(cli, "fetch_trades", fake_fetch)
    rc = main(["scan", "--chains", "ethereum", "--no-color"])
    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert "OK" in out
    assert "no stablecoin depeg" in out


def test_scan_json_with_synthetic_signal(monkeypatch, capsys, usde_eth_address):
    monkeypatch.setenv("CHAINSTREAM_API_KEY", "k")

    def fake_fetch(client, *, chain, tokens, lookback_minutes, limit):
        if chain != "ethereum":
            return [], {}
        return (
            [
                TradeObservation(
                    chain="ethereum",
                    address=usde_eth_address,
                    symbol="USDe",
                    price_usd=0.95,
                    block_time="2026-05-02T00:00:00Z",
                ),
                TradeObservation(
                    chain="ethereum",
                    address=usde_eth_address,
                    symbol="USDe",
                    price_usd=0.95,
                    block_time="2026-05-02T00:01:00Z",
                ),
            ],
            {},
        )

    monkeypatch.setattr(cli, "fetch_trades", fake_fetch)

    rc = main(["scan", "--chains", "ethereum", "--tokens", "USDe", "--json"])
    assert rc == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "stable-depeg-radar/v1"
    assert payload["signal_count"] == 1
    assert payload["signals"][0]["token"] == "USDe"
    assert payload["signals"][0]["severity"] == "critical"
    assert payload["chains"] == ["ethereum"]


def test_scan_propagates_chainstream_error(monkeypatch, capsys):
    from stable_depeg_radar.chainstream import ChainStreamError

    monkeypatch.setenv("CHAINSTREAM_API_KEY", "k")

    def fake_fetch(client, *, chain, tokens, lookback_minutes, limit):
        raise ChainStreamError("boom")

    monkeypatch.setattr(cli, "fetch_trades", fake_fetch)
    rc = main(["scan", "--chains", "ethereum"])
    assert rc == 1
    assert "ChainStream scan failed" in capsys.readouterr().err
