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
    "correlation",
    "sector_rotation",
    "hurst_summary",
    "vol_regime",
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
    "mtf_confluence",
    "thesis_card",
    "hurst",
    "sizing_source",
    "chosen_kelly_f",
    "effective_ATR_mult",
    "vol_regime",
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
    "mtf_confluence",
    "thesis_card",
    "hurst",
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
    "mtf_confluence",
    "thesis_card",
    "hurst",
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
    assert "correlation" in data
    assert isinstance(data["correlation"], dict)
    assert "pairs" in data["correlation"]
    assert "concentration_warning" in data["correlation"]
    assert isinstance(data["correlation"]["concentration_warning"], bool)

    assert "sector_rotation" in data
    assert isinstance(data["sector_rotation"], dict)
    assert "top_sectors" in data["sector_rotation"]
    assert "sector_map" in data["sector_rotation"]

    assert "hurst_summary" in data
    assert isinstance(data["hurst_summary"], dict)
    assert set(data["hurst_summary"].keys()) == {"trending", "random", "meanrev", "unknown"}
    for k, v in data["hurst_summary"].items():
        assert isinstance(v, int)
        assert v >= 0

    assert "vol_regime" in data
    assert isinstance(data["vol_regime"], dict)
    assert set(data["vol_regime"].keys()) == {"bucket", "sigma_ann_pct", "percentile"}
    assert data["vol_regime"]["bucket"] in {"HIGH", "NORMAL", "LOW"}

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
        assert isinstance(sig["thesis_card"], str) and len(sig["thesis_card"]) > 0
        assert isinstance(sig["mtf_confluence"], bool)
        assert "effective_ATR_mult" in sig
        assert "vol_regime" in sig
        assert sig["effective_ATR_mult"] in {3.25, 2.5, 2.125}
        assert sig["vol_regime"] in {"HIGH", "NORMAL", "LOW"}

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
        assert isinstance(wl["thesis_card"], str) and len(wl["thesis_card"]) > 0
        assert isinstance(wl["mtf_confluence"], bool)

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
        assert isinstance(od["thesis_card"], str) and len(od["thesis_card"]) > 0
        assert isinstance(od["mtf_confluence"], bool)
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


def test_hurst_graceful_short_history():
    """
    Hermetic test: A short history fixture (<100 daily bars) returns None,
    never crashes, and does not divide by zero.
    """
    import main
    import pandas as pd
    import numpy as np

    # 1. <100 bars DataFrame
    short_df = pd.DataFrame({"Close": [100.0 + i for i in range(50)]})
    res_short = main.calculate_hurst_exponent(short_df)
    assert res_short is None

    # 2. Empty / None DataFrame
    assert main.calculate_hurst_exponent(None) is None
    assert main.calculate_hurst_exponent(pd.DataFrame()) is None

    # 3. Exactly 99 bars
    df_99 = pd.DataFrame({"Close": [100.0 + i for i in range(99)]})
    assert main.calculate_hurst_exponent(df_99) is None

    # 4. Constant closes (zero variance / division by zero safety)
    const_df = pd.DataFrame({"Close": [100.0] * 120})
    assert main.calculate_hurst_exponent(const_df) is None

    # 5. >=100 bars valid history with price variation produces a float in [0.0, 1.0]
    prices = [100.0]
    for i in range(120):
        # Deterministic variation
        step = 1.01 if (i % 3 != 0) else 0.99
        prices.append(prices[-1] * step)
    valid_df = pd.DataFrame({"Close": prices})
    h = main.calculate_hurst_exponent(valid_df)
    assert h is not None
    assert isinstance(h, float)
    assert 0.0 <= h <= 1.0


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


def test_correlation_and_mtf_diagnostics():
    """
    Hermetic 2-symbol fixture:
    - correlation pairs 0/1 entry no crash
    - thesis_card non-empty string
    - mtf_confluence bool
    - sector_rotation key present
    """
    import main
    # 0 open
    corr_0 = main.compute_open_positions_correlation([])
    assert corr_0["pairs"] == []
    assert corr_0["concentration_warning"] is False

    # 1 open
    corr_1 = main.compute_open_positions_correlation([{"symbol": "AAA.NS", "sector": "NIFTY_IT"}])
    assert corr_1["pairs"] == []
    assert corr_1["concentration_warning"] is False

    # 2 open
    corr_2 = main.compute_open_positions_correlation([
        {"symbol": "AAA.NS", "sector": "NIFTY_IT"},
        {"symbol": "BBB.NS", "sector": "NIFTY_IT"}
    ])
    assert isinstance(corr_2["pairs"], list)
    assert len(corr_2["pairs"]) == 1
    assert corr_2["pairs"][0]["a"] == "AAA.NS"
    assert corr_2["pairs"][0]["b"] == "BBB.NS"
    assert isinstance(corr_2["concentration_warning"], bool)

    # sector rotation
    sec_rot = main.compute_sector_rotation(["AAA.NS", "BBB.NS"])
    assert "top_sectors" in sec_rot
    assert "sector_map" in sec_rot
    assert len(sec_rot["top_sectors"]) > 0

    # mtf confluence
    from tests.test_rules_golden import build_scenario_dataframe
    df_tb = build_scenario_dataframe("textbook")
    mtf_tb = main.calculate_mtf_confluence(df_tb, daily_trend_ok=True)
    assert isinstance(mtf_tb, bool)

    # thesis card
    dummy_item = {
        "Symbol": "TEST.NS",
        "grade": "A",
        "rs_rating": 88,
        "base_maturity": 3,
        "days_in_base": 42,
        "Trend": "YES",
        "Coiling": "YES",
        "SectorBullish": "YES",
        "mtf_confluence": True,
        "inst_footprint": "accumulation",
        "next_event": {"type": "EARNINGS", "days_to_event": 6},
        "Target": 250.0,
        "Stop": 200.0,
    }
    tc = main.build_thesis_card(dummy_item)
    assert isinstance(tc, str)
    assert len(tc) > 0
    lines = tc.split("\n")
    assert len(lines) == 4
    assert "GRADE A | RS 88 | Base 3/4 (42d)" in lines[0]
    assert "Trend ✓ / Setup Coiling / Sector Bullish / MTF ✓" in lines[1]
    assert "Inst: accumulation | Next event: EARNINGS in 6d" in lines[2]
    assert "Risk 1% (gap-capped @20%)" in lines[3]


def test_journal_views_no_crash():
    """
    Hermetic test feeding a 1-trade + 1-open fixture.
    Asserts the render / computation functions return without throwing
    and that heat math = risk / CAPITAL correctly.
    """
    import main

    # 1-open fixture
    open_fixture = [
        {
            "symbol": "TEST1.NS",
            "entry_price": 100.0,
            "stop": 93.0,
            "qty": 100,
            "entry_date": "2026-10-20"
        }
    ]

    # 1-trade fixture
    trade_fixture = [
        {
            "symbol": "TEST1.NS",
            "entry_date": "2026-10-10",
            "exit_date": "2026-10-18",
            "entry_price": 100.0,
            "exit_price": 114.0,
            "stop": 93.0,
            "qty": 100,
            "pnl": 1400.0,
            "r_multiple": 2.0,
            "signal_type": "BREAKOUT",
            "grade": "A",
            "exit_reason": "TARGET",
        }
    ]

    # Portfolio Heat Calculation
    heat = main.compute_portfolio_heat(open_fixture, capital=200000.0, max_heat_pct=0.05)
    expected_risk = (100.0 - 93.0) * 100.0  # 700.0
    expected_pct_capital = round((expected_risk / 200000.0) * 100.0, 2)  # 0.35%

    assert heat["total_risk"] == expected_risk
    assert heat["heat_pct"] == expected_pct_capital
    assert heat["max_heat_budget"] == 10000.0
    assert heat["gauge_pct"] == 7.0
    assert heat["heat_status"] == "green"
    assert len(heat["positions"]) == 1

    # Live Journal Stats Calculation
    stats = main.compute_live_journal_stats(trade_fixture)
    assert stats["total_trades"] == 1
    assert stats["wins"] == 1
    assert stats["losses"] == 0
    assert stats["win_rate"] == 100.0
    assert stats["total_pnl"] == 1400.0
    assert stats["expectancy_r"] == 2.0
    assert stats["tails_captured_pct"] == 100.0
    assert "A" in stats["by_grade"]
    assert "BREAKOUT" in stats["by_signal_type"]
    assert "TARGET" in stats["by_exit_reason"]

    # Assert empty fixtures also execute cleanly without crashing
    empty_heat = main.compute_portfolio_heat([])
    assert empty_heat["total_risk"] == 0.0
    assert empty_heat["heat_pct"] == 0.0

    empty_stats = main.compute_live_journal_stats([])
    assert empty_stats["total_trades"] == 0



