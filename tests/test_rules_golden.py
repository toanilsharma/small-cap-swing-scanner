"""
TEST 1 - tests/test_rules_golden.py
The Heart: Pins the AND-logic of SIGNAL and indicator triggers across 4 distinct market scenarios.
Uses deterministic synthetic OHLCV DataFrames with fixed numpy seed.
"""

import datetime
import json
import os
from typing import Dict, Any
import numpy as np
import pandas as pd
import pytest
import main

GOLDEN_FILE = os.path.join(os.path.dirname(__file__), "GOLDEN_RULES.json")

BOOLEAN_COLUMNS = [
    "TREND_OK",
    "VOL_DRYUP",
    "PRICE_TIGHT",
    "SETUP_OK",
    "SQUEEZE_ON",
    "SETUP_WINDOW",
    "BREAKOUT",
    "VOL_SPIKE",
    "STRONG_CLOSE",
    "PULLBACK",
    "SIGNAL",
    "SIGNAL_PULLBACK",
]


def build_scenario_dataframe(scenario: str) -> pd.DataFrame:
    """
    Generate a 260-bar deterministic synthetic OHLCV DataFrame for a specified scenario.
    Fixed random seed ensures identical numbers across all machines and platforms.
    """
    np.random.seed(42)
    n = 260
    dates = [datetime.date(2025, 1, 1) + datetime.timedelta(days=i) for i in range(n)]

    if scenario == "downtrend":
        # Scenario (b): Steady downtrend from 200 down to 100
        close = np.linspace(200.0, 100.0, n)
        high = close + 1.0
        low = close - 1.0
        open_ = close + 0.2
        volume = np.full(n, 1000000.0)
    else:
        # Base Stage 2 uptrend: 100 to 200 over 240 days
        base = np.linspace(100.0, 200.0, 240)
        plateau = np.full(12, 200.0)
        coiling_days = np.full(7, 201.0)
        close = np.concatenate([base, plateau, coiling_days, [207.0]])

        high = close + 1.0
        low = close - 1.0
        open_ = close.copy()
        volume = np.full(n, 1000000.0)

        # Prior 20-day high: set high of day 242 to 205.0 (becomes HIGH20 ceiling)
        high[242] = 205.0

        # Days 250 to 258: 9 days of coiling / volatility dry-up (tight range=0.3, volume=300,000)
        for j in range(250, 259):
            high[j] = close[j] + 0.15
            low[j] = close[j] - 0.15
            volume[j] = 300000.0

        if scenario == "textbook":
            # Scenario (a): Valid breakout ~1% above prior 20d high (205), volume spike 2.0x, strong close in top 10%
            close[-1] = 207.0
            high[-1] = 207.2
            low[-1] = 204.0
            open_[-1] = 205.0
            volume[-1] = 2000000.0
        elif scenario == "breakout_no_volume":
            # Scenario (c): Identical breakout price but weak volume (~0.8x avg)
            close[-1] = 207.0
            high[-1] = 207.2
            low[-1] = 204.0
            open_[-1] = 205.0
            volume[-1] = 800000.0
        elif scenario == "coil_no_breakout":
            # Scenario (d): Coiling continues, close remains strictly below prior 20d high
            close[-1] = 203.0
            high[-1] = 203.15
            low[-1] = 202.85
            open_[-1] = 203.0
            volume[-1] = 300000.0
        else:
            raise ValueError(f"Unknown scenario: {scenario}")

    df = pd.DataFrame({
        "Date": dates,
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    })
    return df


def compute_all_scenarios() -> Dict[str, Dict[str, bool]]:
    """Compute boolean indicator vector for each scenario's final row."""
    results: Dict[str, Dict[str, bool]] = {}
    for scen in ["textbook", "downtrend", "breakout_no_volume", "coil_no_breakout"]:
        df = build_scenario_dataframe(scen)
        res_df = main.add_indicators(df)
        last_row = res_df.iloc[-1]
        results[scen] = {col: bool(last_row[col]) for col in BOOLEAN_COLUMNS}
    return results


def test_scenario_intent_direct():
    """
    Direct semantic assertions validating trading rules intent across all 4 scenarios.
    Ensures intent is crystal clear even without referencing the serialized golden file.
    """
    scenarios = compute_all_scenarios()

    # (a) Textbook Long: all breakout and setup signals must align
    tb = scenarios["textbook"]
    assert tb["TREND_OK"] is True, "Textbook long must satisfy Stage 2 trend criteria"
    assert tb["SETUP_OK"] is True, "Textbook long must exhibit volume dry-up and price contraction"
    assert tb["SETUP_WINDOW"] is True, "Setup window must be active from prior coiling sessions"
    assert tb["BREAKOUT"] is True, "Close must pierce 20-day high"
    assert tb["VOL_SPIKE"] is True, "Volume must exceed 1.5x 50-day average volume"
    assert tb["STRONG_CLOSE"] is True, "Close must finish in upper 40% of session candle range"
    assert tb["SIGNAL"] is True, "Full AND-condition must trigger valid Breakout SIGNAL"

    # (b) Downtrend: trend filter must fail and signal must be False
    dt = scenarios["downtrend"]
    assert dt["TREND_OK"] is False, "Downtrending stock must fail trend filter"
    assert dt["SIGNAL"] is False, "No signal permitted in downtrend"

    # (c) Breakout without Volume: fails volume spike requirement
    nv = scenarios["breakout_no_volume"]
    assert nv["BREAKOUT"] is True, "Price broke out above 20-day high"
    assert nv["VOL_SPIKE"] is False, "Volume spike must be False when volume is below threshold"
    assert nv["SIGNAL"] is False, "Breakout without institutional volume spike must NOT trigger SIGNAL"

    # (d) Coiling without Breakout: setup is ready but no price trigger
    cb = scenarios["coil_no_breakout"]
    assert cb["SETUP_OK"] is True, "Stock is actively coiling"
    assert cb["BREAKOUT"] is False, "No breakout trigger since price remains below 20-day high"
    assert cb["SIGNAL"] is False, "Coiled stock without breakout must NOT trigger SIGNAL"


def test_golden_rules_match():
    """
    Golden Master Regression Test:
    Compares freshly-computed scenario vectors against tests/GOLDEN_RULES.json.
    Any inadvertent alteration to indicators or signal logic will fail loudly here.
    """
    if not os.path.exists(GOLDEN_FILE):
        pytest.fail(
            f"GOLDEN_RULES.json missing at {GOLDEN_FILE}. "
            "Generate golden first via: python audit.py --regen-golden"
        )

    with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    fresh_data = compute_all_scenarios()

    assert fresh_data == golden_data, (
        f"Indicator/signal boolean contract drifted from golden snapshot!\n"
        f"Expected:\n{json.dumps(golden_data, indent=2)}\n"
        f"Actual:\n{json.dumps(fresh_data, indent=2)}"
    )
