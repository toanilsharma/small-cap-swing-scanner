"""
TEST 2 - tests/test_risk_math.py
Pins position sizing, ATR stop loss, 7% floor cap, and 2R profit targets.
Calls the SAME production code path used by main.scan_symbol by providing synthetic
indicator rows, validating exact numbers without altering main.py.
"""

import math
from typing import Optional, Dict, Any
import numpy as np
import pandas as pd
import pytest
import main


def _invoke_scan_symbol_with_risk_inputs(
    entry: float,
    atr: float,
    monkeypatch: pytest.MonkeyPatch,
    override_signal: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Feeds synthetic entry and atr directly into main.scan_symbol.
    Mocks historical fetch, sector filter, and index return to isolate the risk math.
    """
    n = 260
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    # Rising prices so 50-day stock return is positive (> 0.0 index return)
    if entry > 0:
        close = np.linspace(entry * 0.7, entry, n)
    else:
        close = np.full(n, entry)

    # Ensure daily turnover >= 20 Crores (200,000,000)
    vol = 10000000.0 if entry <= 0 else max(1000000.0, 300000000.0 / max(1.0, entry))

    df = pd.DataFrame({
        "Date": dates,
        "Open": close,
        "High": close + 1.0,
        "Low": close - 1.0,
        "Close": close,
        "Volume": np.full(n, vol),
        "ATR14": np.full(n, atr),
        "RSI14": np.full(n, 55.0),
        "SIGNAL": np.full(n, override_signal),
        "SIGNAL_PULLBACK": np.full(n, False),
    })

    monkeypatch.setattr(main, "get_history", lambda sym: df)
    # Bypass add_indicators recalculation so exact synthetic entry & atr are tested
    monkeypatch.setattr(main, "add_indicators", lambda d: d)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")

    return main.scan_symbol("MOCK.NS")


def test_risk_math_7pct_floor_cap_binds(monkeypatch: pytest.MonkeyPatch):
    """
    Case 1: entry=100, atr=5
    Raw stop = 100 - (2.0 * 5) = 90.0.
    Floored by 9% cap to 91.0 (entry * 0.91).
    Risk per unit = 100 - 91.0 = 9.0.
    Target = 100 + 2 * 9.0 = 118.0.
    Capital = 100,000, Risk = 1% -> Risk budget = 1,000.
    Risk-based Qty = floor(1000 / 9) = 111.
    Gap-based Qty = floor(2500 / 19) = 131.
    Qty = min(111, 131) = 111.
    Risk amount = 111 * 9 = 999.0.
    """
    sig = _invoke_scan_symbol_with_risk_inputs(entry=100.0, atr=5.0, monkeypatch=monkeypatch)
    assert sig is not None, "Signal should be generated for valid entry and ATR"
    assert sig["Entry"] == 100.0
    assert sig["Stop"] == 91.0
    assert sig["Risk Per Unit"] == 9.0
    assert sig["Target"] == 118.0
    assert sig["Qty"] == 111
    assert sig["Risk Amount"] == 999.0


def test_risk_math_atr_stop_above_floor(monkeypatch: pytest.MonkeyPatch):
    """
    Case 2: entry=100, atr=3
    Raw stop = 100 - (2.0 * 3) = 94.0 (above 91.0 floor, so NOT floored).
    Risk per unit = 100 - 94.0 = 6.0.
    Target = 100 + 2 * 6.0 = 112.0.
    Risk-based Qty = floor(1000 / 6) = 166.
    Gap-based Qty = floor(2500 / 19) = 131 (gap survival sizing binds!).
    Qty = min(166, 131) = 131.
    Risk amount = 131 * 6 = 786.0.
    """
    sig = _invoke_scan_symbol_with_risk_inputs(entry=100.0, atr=3.0, monkeypatch=monkeypatch)
    assert sig is not None
    assert sig["Entry"] == 100.0
    assert sig["Stop"] == 94.0
    assert sig["Risk Per Unit"] == 6.0
    assert sig["Target"] == 112.0
    assert sig["Qty"] == 131
    assert sig["Risk Amount"] == 786.0


def test_risk_math_extreme_atr_hard_capped(monkeypatch: pytest.MonkeyPatch):
    """
    Case 3: entry=100, atr=50
    Raw stop = 100 - (2.0 * 50) = 0.0.
    9% rule floors stop to 91.0.
    Risk per unit = 9.0, Target = 118.0, Qty = 111.
    """
    sig = _invoke_scan_symbol_with_risk_inputs(entry=100.0, atr=50.0, monkeypatch=monkeypatch)
    assert sig is not None
    assert sig["Entry"] == 100.0
    assert sig["Stop"] == 91.0
    assert sig["Risk Per Unit"] == 9.0
    assert sig["Target"] == 118.0
    assert sig["Qty"] == 111


@pytest.mark.parametrize("bad_entry, bad_atr", [
    (0.0, 5.0),       # Zero entry
    (-100.0, 5.0),    # Negative entry
    (100.0, 0.0),     # Zero ATR
    (100.0, -2.0),    # Negative ATR
    (100.0, float("nan")),  # NaN ATR
])
def test_risk_math_invalid_inputs_return_none(bad_entry: float, bad_atr: float, monkeypatch: pytest.MonkeyPatch):
    """Invalid price or volatility inputs must cleanly abort and return None."""
    sig = _invoke_scan_symbol_with_risk_inputs(entry=bad_entry, atr=bad_atr, monkeypatch=monkeypatch)
    assert sig is None, f"Expected None for entry={bad_entry}, atr={bad_atr}"


def test_risk_math_zero_qty_returns_none(monkeypatch: pytest.MonkeyPatch):
    """If stop >= entry or risk_per_unit exceeds total risk budget (qty <= 0), returns None."""
    # Sizing for 100,000 capital @ 1% risk gives 1,000 risk budget.
    # If entry=10,000 and atr=1000, risk_per_unit=700 (floored to 7% -> 700). Qty = floor(1000/700)=1.
    # But if risk budget is less than risk_per_unit (e.g. capital=1000, risk_pct=0.01 -> budget=10), qty=floor(10/700)=0
    monkeypatch.setattr(main, "CAPITAL", 1000)
    monkeypatch.setattr(main, "RISK_PCT", 0.01)  # budget = 10 Rs
    sig = _invoke_scan_symbol_with_risk_inputs(entry=1000.0, atr=50.0, monkeypatch=monkeypatch)
    assert sig is None, "When computed qty is 0, scan_symbol must return None"
