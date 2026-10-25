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

EXPECTED_BACKTEST_RESULTS_KEYS = {
    "period",
    "trades",
    "equity_curve",
    "win_rate",
    "avg_win_R",
    "avg_loss_R",
    "expectancy_R",
    "profit_factor",
    "max_drawdown_pct",
    "by_grade",
    "by_signal_type",
    "tail_capture",
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


def test_backtest_schema_drift_and_empty_tolerance(tmp_cwd: Any):
    """
    Schema-drift: assert backtest_results.json schema matches EXPECTED_BACKTEST_RESULTS_KEYS
    AND assert the system is absent/empty-tolerant when no archive exists.
    """
    import backtest

    # 1. Absence tolerance: when no archive exists, run_backtest returns clean empty schema
    empty_res = backtest.run_backtest(archive_dfs={})
    assert isinstance(empty_res, dict)
    assert set(empty_res.keys()) == EXPECTED_BACKTEST_RESULTS_KEYS
    assert empty_res["trades"] == []
    assert empty_res["win_rate"] == 0.0

    # 2. Schema check on emitted backtest_results.json
    out_file = "backtest_results.json"
    backtest.run_backtest(archive_dfs={}, out_file=out_file)
    assert os.path.exists(out_file)
    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert set(data.keys()) == EXPECTED_BACKTEST_RESULTS_KEYS


def test_archive_ohlcv_append_and_deduplicate(tmp_cwd: Any):
    """
    Assert that archive_ohlcv appends daily bars, preserves correct gzip schema,
    and deduplicates strictly by (date, symbol) keeping newest.
    """
    import datetime
    import pandas as pd
    from scripts import archive_ohlcv

    test_date = datetime.date(2025, 6, 15)
    rows_day1 = [
        {"date": "2025-06-15", "symbol": "TEST1.NS", "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 50000},
        {"date": "2025-06-15", "symbol": "TEST2.NS", "open": 50.0, "high": 55.0, "low": 48.0, "close": 52.0, "volume": 20000},
    ]
    path1 = archive_ohlcv.append_bars_to_archive(rows_day1, target_date=test_date)
    assert os.path.exists(path1)

    df1 = pd.read_csv(path1, compression="gzip")
    assert len(df1) == 2
    assert list(df1.columns) == ["date", "symbol", "open", "high", "low", "close", "volume"]

    # Append duplicate date + symbol (updated close) and new bar
    rows_day2 = [
        {"date": "2025-06-15", "symbol": "TEST1.NS", "open": 100.0, "high": 106.0, "low": 99.0, "close": 104.0, "volume": 60000},
        {"date": "2025-06-16", "symbol": "TEST1.NS", "open": 104.0, "high": 110.0, "low": 103.0, "close": 108.0, "volume": 70000},
    ]
    path2 = archive_ohlcv.append_bars_to_archive(rows_day2, target_date=test_date)
    df2 = pd.read_csv(path2, compression="gzip")
    assert len(df2) == 3
    test1_june15 = df2[(df2["symbol"] == "TEST1.NS") & (df2["date"] == "2025-06-15")].iloc[0]
    assert test1_june15["close"] == 104.0


