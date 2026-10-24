"""
TEST 6 - tests/test_schema_drift.py
Guards against schema drift and field renaming between the Python backend and Netlify dashboard.
Asserts the exact set of keys in scan_results.json, signals, and watchlist candidates.
"""

import json
import os
from typing import Any
import pytest
from tests.test_hermetic_scan import execute_full_scan_pipeline


EXPECTED_TOP_LEVEL_KEYS = {
    "updated_at",
    "market_ok",
    "signals",
    "watchlist",
    "scanned_count",
    "market_summary",
    "on_deck",
    "leaders_board",
    "inst_summary",
    "deals_stale",
    "landmines",
}

EXPECTED_MARKET_SUMMARY_KEYS = {
    "source",
    "last_close",
    "prev_close",
    "chg_pct",
    "last_bar_date",
    "as_of_ist",
    "breadth_above_sma50",
    "breadth_above_sma200",
    "universe_size",
    "advancers",
    "decliners",
    "unchanged",
}

EXPECTED_SIGNAL_KEYS = {
    "Signal Date",
    "Symbol",
    "Sector",
    "Type",
    "Close",
    "Entry",
    "Stop",
    "Target",
    "Qty",
    "Risk Per Unit",
    "Risk Amount",
    "ATR14",
    "RSI14",
    "catalyst",
    "adv20_cr",
    "gap_qty_applied",
    "next_earnings",
    "circuit_skipped_reason",
    "rs_rating",
    "base_maturity",
    "days_in_base",
    "inst_footprint",
    "next_event",
    "warn_event",
}

EXPECTED_WATCHLIST_KEYS = {
    "Symbol",
    "Sector",
    "SectorBullish",
    "Trend",
    "Coiling",
    "DistToBreakout%",
    "Close",
    "VolDryup",
    "RsiInRange",
    "RSI14",
    "ATR14",
    "score",
    "grade",
    "Score",
    "Grade",
    "rs_rating",
    "base_maturity",
    "days_in_base",
    "inst_footprint",
    "next_event",
    "warn_event",
}

EXPECTED_ON_DECK_KEYS = {
    "symbol",
    "close",
    "breakout_level",
    "dist_pct",
    "missing_condition",
    "atr14",
    "rsi14",
    "inst_footprint",
    "next_event",
    "warn_event",
}


def test_schema_keys_exact_match(tmp_cwd: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Ensures that scan_results.json top-level, signals, and watchlist entries
    produce the exact contract expected by dashboard/app.js.
    """
    monkeypatch.setenv("QUIET", "1")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")

    signals, watchlist, count, mkt_ok = execute_full_scan_pipeline()

    with open("scan_results.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Top-level keys
    actual_top_keys = set(data.keys())
    assert actual_top_keys == EXPECTED_TOP_LEVEL_KEYS, (
        f"Top-level schema drift detected!\n"
        f"Missing: {EXPECTED_TOP_LEVEL_KEYS - actual_top_keys}\n"
        f"Unexpected: {actual_top_keys - EXPECTED_TOP_LEVEL_KEYS}"
    )

    # 2. Signals schema
    assert len(data["signals"]) > 0, "Expected at least one signal in hermetic scan"
    for sig in data["signals"]:
        actual_sig_keys = set(sig.keys())
        assert actual_sig_keys == EXPECTED_SIGNAL_KEYS, (
            f"Signal item schema drift in {sig.get('Symbol')}!\n"
            f"Missing: {EXPECTED_SIGNAL_KEYS - actual_sig_keys}\n"
            f"Unexpected: {actual_sig_keys - EXPECTED_SIGNAL_KEYS}"
        )
        # rs_rating may be None at N=2 in small universes
        assert "rs_rating" in sig

    # 3. Watchlist schema
    assert len(data["watchlist"]) > 0, "Expected at least one watchlist candidate in hermetic scan"
    for wl in data["watchlist"]:
        actual_wl_keys = set(wl.keys())
        assert actual_wl_keys == EXPECTED_WATCHLIST_KEYS, (
            f"Watchlist item schema drift in {wl.get('Symbol')}!\n"
            f"Missing: {EXPECTED_WATCHLIST_KEYS - actual_wl_keys}\n"
            f"Unexpected: {actual_wl_keys - EXPECTED_WATCHLIST_KEYS}"
        )
        assert "rs_rating" in wl

    # 4. Market summary schema
    assert isinstance(data["market_summary"], dict)
    actual_market_summary_keys = set(data["market_summary"].keys())
    assert actual_market_summary_keys == EXPECTED_MARKET_SUMMARY_KEYS, (
        f"Market summary schema drift!\n"
        f"Missing: {EXPECTED_MARKET_SUMMARY_KEYS - actual_market_summary_keys}\n"
        f"Unexpected: {actual_market_summary_keys - EXPECTED_MARKET_SUMMARY_KEYS}"
    )

    # 5. On-deck & leaders board
    assert isinstance(data["on_deck"], list)
    for od in data["on_deck"]:
        actual_od_keys = set(od.keys())
        assert actual_od_keys == EXPECTED_ON_DECK_KEYS, (
            f"On-deck item schema drift in {od.get('symbol')}!\n"
            f"Missing: {EXPECTED_ON_DECK_KEYS - actual_od_keys}\n"
            f"Unexpected: {actual_od_keys - EXPECTED_ON_DECK_KEYS}"
        )
    assert isinstance(data["leaders_board"], list)


def test_inst_footprint_failopen_unknown(tmp_cwd: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Fail-open guarantee: If deals.json is missing or corrupt,
    classify_inst_footprint returns 'unknown' for all symbols,
    the pipeline still writes scan_results.json, and no exception is raised.
    """
    import main
    monkeypatch.setenv("QUIET", "1")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")

    # Ensure deals.json is absent
    if os.path.exists("deals.json"):
        os.remove("deals.json")

    signals, watchlist, count, mkt_ok = execute_full_scan_pipeline()

    assert os.path.exists("scan_results.json")
    with open("scan_results.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["deals_stale"] is True
    assert "inst_summary" in data
    assert data["inst_summary"]["unknown_count"] >= 0
    for s in data["signals"]:
        assert s["inst_footprint"] == "unknown"
    for w in data["watchlist"]:
        assert w["inst_footprint"] == "unknown"
    for o in data["on_deck"]:
        assert o["inst_footprint"] == "unknown"


def test_rs_graceful_small_universe():
    """
    Assert that calculate_rs_rating returns None gracefully when universe < 30.
    At N=2, rs_rating is None for all symbols and does not crash or raise exceptions.
    """
    import main
    res = main.calculate_rs_rating(["AAA.NS", "BBB.NS"])
    assert res == {"AAA.NS": None, "BBB.NS": None}

