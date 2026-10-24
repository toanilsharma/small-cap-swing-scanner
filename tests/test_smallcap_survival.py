"""
TEST 8 - tests/test_smallcap_survival.py
Small-Cap Survival Layer offline validation:
1. Equal-weight basket regime fail-closed (<80% symbols -> regime_ok False).
2. Gap / circuit survival sizing (high-volatility -> gap_based_qty binds).
3. Position-aware liquidity (notional > 1.0% ADV -> rejected).
4. Earnings blackout fail-closed (unknown earnings -> entry blocked).
5. Heat cap / concurrent limits block /buy (4th concurrent / >5% heat -> rejected).
6. Monthly stop limit blocks /buy (realized + unrealized month loss >= 6% -> rejected).
"""

import datetime
import json
import os
from typing import Any, Dict, List
import numpy as np
import pandas as pd
import pytest
import main


def _create_synthetic_symbol_df(
    entry: float = 100.0,
    atr: float = 4.0,
    n_days: int = 260,
    turnover_rupees: float = 100_000_000.0,
    is_signal: bool = True
) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=n_days, freq="D")
    close = np.linspace(entry * 0.7, entry, n_days)
    vol = max(1000.0, turnover_rupees / max(1.0, entry))

    df = pd.DataFrame({
        "Date": dates,
        "Open": close,
        "High": close + 1.0,
        "Low": close - 1.0,
        "Close": close,
        "Volume": np.full(n_days, vol),
        "ATR14": np.full(n_days, atr),
        "RSI14": np.full(n_days, 55.0),
        "SIGNAL": np.full(n_days, is_signal),
        "SIGNAL_PULLBACK": np.full(n_days, False),
    })
    return df


def test_regime_basket_failclosed(monkeypatch: pytest.MonkeyPatch):
    """
    Basket with <80% valid symbols must fail-closed (regime_ok == False).
    Universe has 10 symbols, but only 5 have valid history.
    """
    symbols = [f"SYM{i}.NS" for i in range(10)]
    monkeypatch.setattr(main, "get_symbols", lambda: symbols)

    # Only 5 out of 10 symbols have valid data (50% < 80% threshold)
    def mock_get_history(sym: str):
        idx = int(sym.replace("SYM", "").replace(".NS", ""))
        if idx < 5:
            return _create_synthetic_symbol_df()
        return None

    monkeypatch.setattr(main, "get_history", mock_get_history)
    monkeypatch.setattr(main, "regime_ok", getattr(main, "_real_regime_ok", main.regime_ok))
    main._BASKET_CACHE = None

    basket_df = main.get_basket_df(force_rebuild=True)
    assert basket_df is None, "Basket must be None when <80% of symbols are available"
    assert main.regime_ok() is False, "Regime filter must fail-closed when basket is unavailable"


def test_gap_sizing_min(monkeypatch: pytest.MonkeyPatch):
    """
    A high-volatility / tight-stop name where gap_based_qty < risk_based_qty:
    final qty MUST equal gap_based_qty, and gap_qty_applied must be True.
    """
    entry = 100.0
    atr = 2.0  # Raw stop = 100 - (2.5 * 2.0) = 95.0; above 91.0 floor
    # Stop = 95.0 (above floor). Risk per unit = 5.0
    # Capital = 200,000, Risk = 1% -> Risk budget = 2,000.
    # risk_based_qty = floor(2000 / 5) = 400.
    # gap_based_qty = floor( (200,000 * 0.025) / (100 * 0.20) ) = floor(5000 / 20) = 250.
    # Since 250 < 400, gap_based_qty binds!

    df = _create_synthetic_symbol_df(entry=entry, atr=atr, turnover_rupees=200_000_000.0)

    monkeypatch.setattr(main, "get_history", lambda sym: df)
    monkeypatch.setattr(main, "add_indicators", lambda d: d)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")

    sig = main.scan_symbol("GAPNAME.NS")
    assert sig is not None, "Signal should be generated"
    assert sig["Qty"] == 250, f"Expected gap_based_qty 250 to bind, got {sig['Qty']}"
    assert sig["gap_qty_applied"] is True, "gap_qty_applied must be True when gap sizing binds"


def test_liquidity_size_aware(monkeypatch: pytest.MonkeyPatch):
    """
    When position notional (qty * entry) exceeds 1.0% of ADV20, signal must be rejected.
    """
    entry = 100.0
    atr = 5.0
    # ADV20 = 50,000,000 (minimum 5 crore floor)
    # max_position_value = 0.01 * 50,000,000 = 500,000
    df = _create_synthetic_symbol_df(entry=entry, atr=atr, turnover_rupees=50_000_000.0)

    monkeypatch.setattr(main, "get_history", lambda sym: df)
    monkeypatch.setattr(main, "add_indicators", lambda d: d)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")

    # With CAPITAL = 10,000,000 (1 Crore):
    # risk budget = 100,000 -> qty = floor(100,000 / 9) = 11,111
    # notional = 11,111 * 100 = 1,111,100 > 500,000 (exceeds 1.0% of ADV20)
    monkeypatch.setattr(main, "CAPITAL", 10_000_000)

    sig = main.scan_symbol("ILLIQUID.NS")
    assert sig is None, "Signal must be rejected when notional exceeds 1.0% of ADV20"


def test_earnings_unknown_blocks(monkeypatch: pytest.MonkeyPatch):
    """
    Fail-closed earnings rule:
    If a symbol has NO entry in earnings_dates.json (unknown earnings), entry must be BLOCKED.
    """
    df = _create_synthetic_symbol_df(entry=100.0, atr=5.0)

    monkeypatch.setattr(main, "get_history", lambda sym: df)
    monkeypatch.setattr(main, "add_indicators", lambda d: d)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    # Symbol has no entry in earnings dates -> returns None
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: None)

    is_blocked, reason = main.check_earnings_blackout("MYSTERY.NS", datetime.date(2026, 10, 18))
    assert is_blocked is True, "Unknown earnings must block entry"
    assert "UNKNOWN" in reason

    sig = main.scan_symbol("MYSTERY.NS")
    assert sig is None, "Signal must be blocked when earnings date is unknown"


def test_heat_cap_blocks_buy(tmp_cwd: Any):
    """
    Heat and concurrency limits must reject /buy:
    (a) 4th concurrent small-cap position is rejected (MAX_CONCURRENT_SMALLCAP = 3).
    (b) Trade that causes total open heat to exceed 5% is rejected.
    """
    today_str = datetime.date.today().isoformat()

    # Case A: 3 open positions already exist
    open_positions = [
        {"symbol": f"P{i}.NS", "entry_date": today_str, "entry_price": 100.0, "qty": 10, "stop": 91.0}
        for i in range(3)
    ]
    main.save_open_positions(open_positions)
    main.save_trades([])

    reply_concurrent = main.handle_telegram_command("/buy NEWPOS 100 10 91")
    assert "BUY REJECTED" in reply_concurrent, "4th concurrent position must be rejected"
    assert "Maximum concurrent" in reply_concurrent

    # Case B: Exceeding 5% total heat limit (Capital = 200,000 -> 5% = 10,000)
    # 1 open position with 9,000 risk (4.5% heat)
    single_open = [
        {"symbol": "HIGH_HEAT.NS", "entry_date": today_str, "entry_price": 100.0, "qty": 1000, "stop": 91.0}  # risk = 9 * 1000 = 9,000
    ]
    main.save_open_positions(single_open)

    # Proposed trade adds risk: qty=200, entry=100, stop=91 -> risk = 9 * 200 = 1,800 -> total = 10,800 > 10,000
    reply_heat = main.handle_telegram_command("/buy SECOND 100 200 91")
    assert "BUY REJECTED" in reply_heat, "Trade pushing total heat > 5% must be rejected"
    assert "Total open risk" in reply_heat


def test_monthly_stop_blocks(tmp_cwd: Any):
    """
    Elder circuit-breaker:
    When realized + unrealized losses in the current month hit or exceed 6% of capital (12,000 on 200k),
    /buy must be rejected.
    """
    # Position with 13,000 unrealized loss (6.5% of 200k capital)
    # Entry 100, current 35, qty 200 -> unrealized loss = 13,000
    open_positions = [
        {"symbol": "DRAWDOWN.NS", "entry_price": 100.0, "current_price": 35.0, "qty": 200, "stop": 95.0}
    ]
    main.save_open_positions(open_positions)
    main.save_trades([])

    reply = main.handle_telegram_command("/buy ATTEMPT 100 10 91")
    assert "BUY REJECTED" in reply, "Monthly loss >= 6% must block /buy"
    assert "Monthly drawdown limit" in reply


def test_event_entry_blocks(monkeypatch: pytest.MonkeyPatch, tmp_cwd: Any):
    """
    Event Radar entry gate:
    A synthetic corporate gap-event (e.g. LOCKIN, AGM) scheduled within EARNINGS_BLACKOUT_DAYS (e.g. 2 days)
    must BLOCK entry, mirroring the fail-closed earnings blackout behavior.
    """
    df = _create_synthetic_symbol_df(entry=100.0, atr=4.0)
    today = datetime.date.today()
    df["Date"] = pd.date_range(end=today, periods=len(df), freq="D")
    lockin_date = (today + datetime.timedelta(days=2)).isoformat()
    safe_earnings_date = (today + datetime.timedelta(days=45)).isoformat()

    monkeypatch.setattr(main, "get_history", lambda sym: df)
    monkeypatch.setattr(main, "add_indicators", lambda d: d)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: safe_earnings_date)

    events_data = {
        "LOCKIN_SYM.NS": [
            {"type": "LOCKIN", "date": lockin_date, "note": "Promoter lock-in expiry"}
        ]
    }
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(events_data, f)

    is_blocked, reason = main.check_event_or_earnings_blackout("LOCKIN_SYM.NS", today)
    assert is_blocked is True, "Imminent LOCKIN 2d out must block entry"
    assert "LOCKIN" in reason

    sig = main.scan_symbol("LOCKIN_SYM.NS")
    assert sig is None, "Signal must be blocked when gap-event is within blackout window"


def test_event_open_warns_not_exits(tmp_cwd: Any):
    """
    Event Radar open-position warning:
    When an open position has an imminent event (days_to_event <= 3),
    warn_event must be set to True and a warning message generated,
    BUT the position remains open with its original stop and target (NEVER force-closed).
    """
    today = datetime.date.today()
    agm_date = (today + datetime.timedelta(days=2)).isoformat()

    events_data = {
        "HELD.NS": [
            {"type": "AGM", "date": agm_date, "note": "Annual General Meeting"}
        ]
    }
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(events_data, f)

    open_positions = [
        {
            "symbol": "HELD.NS",
            "entry_date": (today - datetime.timedelta(days=10)).isoformat(),
            "entry_price": 150.0,
            "qty": 50,
            "stop": 139.5,
            "target": 171.0,
        }
    ]

    updated_positions, warn_lines = main.check_open_positions_events(open_positions, today)

    assert len(updated_positions) == 1
    pos = updated_positions[0]
    assert pos["warn_event"] is True
    assert pos["next_event"] is not None
    assert pos["next_event"]["type"] == "AGM"
    assert pos["next_event"]["days_to_event"] == 2

    # CRITICAL: Verify trade math/stops are NOT modified and position is NOT closed
    assert pos["stop"] == 139.5, "Original stop price must be preserved"
    assert pos["target"] == 171.0, "Original target price must be preserved"
    assert pos["qty"] == 50, "Position quantity must remain intact"

    # Verify EOD warning line
    assert len(warn_lines) == 1
    assert "🔔 HELD.NS event (AGM) in 2 days" in warn_lines[0]

