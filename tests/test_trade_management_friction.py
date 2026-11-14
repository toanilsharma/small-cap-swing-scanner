"""
tests/test_trade_management_friction.py
Validates:
1. Indian Statutory Friction (0.30% round-trip) & Net PnL Accounting in /sell, /trades, and /stats.
2. Automated Position Management Alerts:
   - 🟢 RATCHET SL TO BREAKEVEN+FEES (+1.0R)
   - 💰 BOOK 50% AT +2R (+2.0R target)
   - ⏳ 5-DAY TIME STOP TRIGGERED (days_held >= 5, Close <= Entry, Close < EMA10)
   - ⚠️ EARNINGS LOCKOUT EXIT (days_to_earnings <= 3)
   - 🚨 EMA20 RUNNER EXIT (runner < EMA20)
3. Execution Mode Tagging:
   - [PRE-BREAKOUT COIL — PLACE GTT @ PIVOT]
   - [CONFIRMED EOD BREAKOUT — ENTER NEXT OPEN IF GAP <= 1.5%]
"""

import datetime
import json
import pandas as pd
import pytest
import main


def test_statutory_friction_and_net_pnl_sell_command(tmp_cwd, monkeypatch):
    """
    Validate /sell calculates 0.30% round-trip turnover friction:
    turnover = entry * qty + exit * qty
    friction = turnover * 0.0015
    net_pnl = gross_pnl - friction
    """
    entry_price = 1000.0
    exit_price = 1100.0
    qty = 50
    stop = 930.0  # Risk per unit = 70.0, Initial Risk = 3,500.0

    # 1. Open position
    open_pos = [{
        "symbol": "TESTCO.NS",
        "entry_date": "2026-10-01",
        "entry_price": entry_price,
        "qty": qty,
        "stop": stop,
        "planned_stop": stop,
        "target": 1240.0,
        "tags": ["#breakout", "#plan_followed"],
    }]
    main.save_open_positions(open_pos)

    # 2. Execute /sell
    res = main.handle_command("/sell TESTCO 1100 Exited at +10% target")
    assert "TARGET 2R" in res.upper() or "POSITION CLOSED" in res.upper()
    assert "Gross PnL:" in res
    assert "Statutory Friction (0.30%):" in res
    assert "Net PnL:" in res

    # 3. Check trades.json
    trades = main.load_trades()
    assert len(trades) == 1
    t = trades[0]

    expected_turnover = (1000.0 * 50) + (1100.0 * 50)  # 50,000 + 55,000 = 105,000.0
    expected_friction = round(105000.0 * 0.0015, 2)    # 157.50
    expected_gross_pnl = 5000.0
    expected_net_pnl = round(expected_gross_pnl - expected_friction, 2)  # 4842.50
    expected_net_return_pct = round((expected_net_pnl / 50000.0) * 100.0, 2)  # 9.69%

    assert t["turnover"] == expected_turnover
    assert t["statutory_friction"] == expected_friction
    assert t["gross_pnl"] == expected_gross_pnl
    assert t["net_pnl"] == expected_net_pnl
    assert t["pnl"] == expected_net_pnl
    assert t["pnl_pct"] == expected_net_return_pct
    assert t["net_return_pct"] == expected_net_return_pct

    # Initial risk = (1000 - 930) * 50 = 3500.0
    # Net R-mult = 4842.50 / 3500.0 = +1.38R
    assert t["net_r_multiple"] == round(4842.50 / 3500.0, 2)


def test_stats_command_uses_net_pnl(tmp_cwd, monkeypatch):
    """
    Validate /stats aggregates metrics (Win Rate, Profit Factor, Expectancy, Equity Curve)
    strictly from net_pnl after statutory friction.
    """
    trade1 = {
        "symbol": "WIN.NS",
        "entry_date": "2026-10-01",
        "entry_price": 100.0,
        "qty": 100,
        "exit_date": "2026-10-05",
        "exit_price": 120.0,
        "gross_pnl": 2000.0,
        "turnover": 22000.0,
        "statutory_friction": 33.0,
        "net_pnl": 1967.0,
        "pnl": 1967.0,
        "pnl_pct": 19.67,
        "net_return_pct": 19.67,
        "r_multiple": 2.0,
    }
    trade2 = {
        "symbol": "LOSS.NS",
        "entry_date": "2026-10-02",
        "entry_price": 100.0,
        "qty": 100,
        "exit_date": "2026-10-06",
        "exit_price": 93.0,
        "gross_pnl": -700.0,
        "turnover": 19300.0,
        "statutory_friction": 28.95,
        "net_pnl": -728.95,
        "pnl": -728.95,
        "pnl_pct": -7.29,
        "net_return_pct": -7.29,
        "r_multiple": -1.0,
    }
    main.save_trades([trade1, trade2])

    stats_msg = main.handle_command("/stats")
    assert "Win Rate: 50.0%" in stats_msg
    # Total net PnL = 1967.0 - 728.95 = 1238.05
    assert "₹1,238.05" in stats_msg or "1238.05" in stats_msg


def test_position_management_alerts_ratchet_breakeven():
    """
    Badge 1: 🟢 RATCHET SL TO BREAKEVEN+FEES
    Triggered when Close >= Entry + 1.0R -> Move SL to Entry * 1.0035
    """
    entry = 200.0
    stop = 186.0  # 1.0R = 14.0, threshold = 214.0
    open_pos = [{
        "symbol": "RATCHET.NS",
        "entry_date": "2026-10-10",
        "entry_price": entry,
        "qty": 50,
        "stop": stop,
        "target": 228.0,
    }]

    # History where Close = 215.0 (>= 214.0)
    dates = pd.date_range("2026-10-01", periods=15)
    df = pd.DataFrame({
        "Date": dates,
        "Open": [200.0]*14 + [212.0],
        "High": [202.0]*14 + [216.0],
        "Low": [198.0]*14 + [211.0],
        "Close": [200.0]*14 + [215.0],
        "Volume": [100000.0]*15,
    })
    main.add_indicators(df)

    original_get_history = main.get_history
    main.get_history = lambda sym: df.copy()
    try:
        alerts = main.generate_position_management_alerts(open_pos, current_date=datetime.date(2026, 10, 15))
        assert len(alerts) >= 1
        ratchet_alert = [a for a in alerts if "RATCHET SL TO BREAKEVEN+FEES" in a]
        assert len(ratchet_alert) == 1
        assert "200.70" in ratchet_alert[0]  # 200 * 1.0035 = 200.70
    finally:
        main.get_history = original_get_history


def test_position_management_alerts_book_2r():
    """
    Badge 2: 💰 BOOK 50% AT +2R
    Triggered when High >= Target_2R
    """
    entry = 100.0
    target_2r = 114.0
    open_pos = [{
        "symbol": "TARGET2R.NS",
        "entry_date": "2026-10-10",
        "entry_price": entry,
        "qty": 100,
        "stop": 93.0,
        "target": target_2r,
    }]

    dates = pd.date_range("2026-10-01", periods=15)
    df = pd.DataFrame({
        "Date": dates,
        "Open": [100.0]*14 + [110.0],
        "High": [102.0]*14 + [115.0],  # 115.0 >= 114.0
        "Low": [98.0]*14 + [109.0],
        "Close": [100.0]*14 + [113.5],
        "Volume": [100000.0]*15,
    })
    main.add_indicators(df)

    original_get_history = main.get_history
    main.get_history = lambda sym: df.copy()
    try:
        alerts = main.generate_position_management_alerts(open_pos, current_date=datetime.date(2026, 10, 15))
        book_alerts = [a for a in alerts if "BOOK 50% AT +2R" in a]
        assert len(book_alerts) == 1
        assert "Target" in book_alerts[0] or "Sell 50%" in book_alerts[0]
    finally:
        main.get_history = original_get_history


def test_position_management_alerts_5day_time_stop():
    """
    Badge 3: ⏳ 5-DAY TIME STOP TRIGGERED
    Triggered when days_held >= 5 AND Close <= Entry AND Close < EMA10
    """
    entry = 500.0
    open_pos = [{
        "symbol": "DEADMONEY.NS",
        "entry_date": "2026-10-01",
        "entry_price": entry,
        "qty": 20,
        "stop": 460.0,
        "target": 580.0,
    }]

    # 15 days of data, last close = 495.0 (<= 500), EMA10 = 505.0
    dates = pd.date_range("2026-09-25", periods=20)
    closes = [510.0]*18 + [502.0, 495.0]
    df = pd.DataFrame({
        "Date": dates,
        "Open": closes,
        "High": [c + 2.0 for c in closes],
        "Low": [c - 2.0 for c in closes],
        "Close": closes,
        "Volume": [100000.0]*20,
    })
    main.add_indicators(df)

    original_get_history = main.get_history
    main.get_history = lambda sym: df.copy()
    try:
        # Date is 2026-10-10 -> days_held = 9 (>= 5)
        alerts = main.generate_position_management_alerts(open_pos, current_date=datetime.date(2026, 10, 10))
        time_alerts = [a for a in alerts if "5-DAY TIME STOP TRIGGERED" in a]
        assert len(time_alerts) == 1
        assert "Liquidate dead-money" in time_alerts[0]

        # Contrast: if price is holding ABOVE EMA10, time stop must NOT trigger
        df_healthy = df.copy()
        df_healthy.loc[df_healthy.index[-1], "Close"] = 512.0  # Above entry & EMA10
        main.get_history = lambda sym: df_healthy.copy()
        alerts_healthy = main.generate_position_management_alerts(open_pos, current_date=datetime.date(2026, 10, 10))
        assert not any("5-DAY TIME STOP TRIGGERED" in a for a in alerts_healthy)
    finally:
        main.get_history = original_get_history


def test_position_management_alerts_earnings_lockout(monkeypatch):
    """
    Badge 4: ⚠️ EARNINGS LOCKOUT EXIT
    Triggered when days_to_earnings <= 3
    """
    open_pos = [{
        "symbol": "EARNWARN.NS",
        "entry_date": "2026-10-10",
        "entry_price": 300.0,
        "qty": 40,
        "stop": 280.0,
        "target": 340.0,
    }]

    dates = pd.date_range("2026-10-01", periods=15)
    df = pd.DataFrame({
        "Date": dates,
        "Open": [300.0]*15,
        "High": [305.0]*15,
        "Low": [295.0]*15,
        "Close": [302.0]*15,
        "Volume": [100000.0]*15,
    })
    main.add_indicators(df)

    monkeypatch.setattr(main, "get_history", lambda sym: df.copy())
    monkeypatch.setattr(main, "get_next_event", lambda sym, cur_dt: {"type": "EARNINGS", "days_to_event": 2})

    alerts = main.generate_position_management_alerts(open_pos, current_date=datetime.date(2026, 10, 15))
    earn_alerts = [a for a in alerts if "EARNINGS LOCKOUT EXIT" in a]
    assert len(earn_alerts) == 1
    assert "in 2 days" in earn_alerts[0]


def test_position_management_alerts_runner_ema20():
    """
    Badge 5: 🚨 EMA20 RUNNER EXIT
    Triggered on runner position when Close < EMA20
    """
    open_pos = [{
        "symbol": "RUNNER.NS",
        "entry_date": "2026-09-15",
        "entry_price": 100.0,
        "qty": 25,
        "stop": 100.35,
        "target": 120.0,
        "runner": True,
        "tags": ["#runner"],
    }]

    dates = pd.date_range("2026-09-01", periods=30)
    # EMA20 will be around 112, last close breaks down to 108
    closes = [100.0 + i*0.8 for i in range(29)] + [108.0]
    df = pd.DataFrame({
        "Date": dates,
        "Open": closes,
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [150000.0]*30,
    })
    main.add_indicators(df)

    original_get_history = main.get_history
    main.get_history = lambda sym: df.copy()
    try:
        alerts = main.generate_position_management_alerts(open_pos, current_date=datetime.date(2026, 10, 10))
        runner_alerts = [a for a in alerts if "EMA20 RUNNER EXIT" in a]
        assert len(runner_alerts) == 1
        assert "below rising 20-EMA" in runner_alerts[0]
    finally:
        main.get_history = original_get_history


def test_execution_mode_tagging_pre_breakout_coil(monkeypatch):
    """
    Validate [PRE-BREAKOUT COIL — PLACE GTT @ PIVOT] tagging:
    Price within -1.0% to 0.0% below 20-day high pivot with VCP active.
    """
    # 260 bars where HIGH20 = 200.0, current close = 199.0 (-0.5% away)
    dates = pd.date_range("2025-01-01", periods=260)
    close = [150.0 + i*0.2 for i in range(240)] + [198.0]*19 + [199.0]
    high = [c + 1.0 for c in close]
    high[245] = 200.0  # 20-day high pivot = 200.0
    low = [c - 1.0 for c in close]
    # Volatility contraction
    for j in range(250, 260):
        high[j] = close[j] + 0.1
        low[j] = close[j] - 0.1

    df = pd.DataFrame({
        "Date": dates,
        "Open": close,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": [100000.0]*250 + [20000.0]*10,
    })
    main.add_indicators(df)

    monkeypatch.setattr(main, "get_history", lambda sym: df.copy())
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "market_ok", lambda: True)

    diag = main.diagnose("COIL_STOCK.NS")
    assert diag is not None
    assert diag["execution_mode"] == "[PRE-BREAKOUT COIL — PLACE GTT @ PIVOT]"

    # Verify formatting in build_watchlist_text
    wl_text = main.build_watchlist_text([diag])
    assert "[PRE-BREAKOUT COIL — PLACE GTT @ PIVOT]" in wl_text
