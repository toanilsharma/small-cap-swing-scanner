"""
TEST 7 - tests/test_thresholds_locked.py
Regression safety lock on literal module-level numeric and boolean constants.
Guarantees that a silent dial-change or accidental edit to core parameters
immediately fails the logic audit.
"""

import main


def test_core_trading_constants():
    """
    Assert that the foundational numeric thresholds in main.py equal their locked values.
    """
    assert main.VOLUME_SPIKE_MULTIPLIER == 1.5, f"VOLUME_SPIKE_MULTIPLIER changed: {main.VOLUME_SPIKE_MULTIPLIER}"
    assert main.MAX_STOP_LOSS_PCT == 0.07, f"MAX_STOP_LOSS_PCT changed: {main.MAX_STOP_LOSS_PCT}"
    assert main.ATR_STOP_MULTIPLIER == 1.5, f"ATR_STOP_MULTIPLIER changed: {main.ATR_STOP_MULTIPLIER}"
    assert main.TARGET_R_MULTIPLE == 2.0, f"TARGET_R_MULTIPLE changed: {main.TARGET_R_MULTIPLE}"
    assert main.RISK_PCT == 0.01, f"RISK_PCT changed: {main.RISK_PCT}"
    assert main.CAPITAL == 100000, f"CAPITAL changed: {main.CAPITAL}"
    assert main.SETUP_WINDOW_DAYS == 10, f"SETUP_WINDOW_DAYS changed: {main.SETUP_WINDOW_DAYS}"
    assert main.MIN_AVG_TURNOVER == 200000000, f"MIN_AVG_TURNOVER changed: {main.MIN_AVG_TURNOVER}"


def test_core_flags_and_index_symbol():
    """
    Assert that setup enablement flags and the benchmark index symbol remain locked.
    """
    assert main.ENABLE_PULLBACK is True, f"ENABLE_PULLBACK changed: {main.ENABLE_PULLBACK}"
    assert main.ENABLE_SQUEEZE is True, f"ENABLE_SQUEEZE changed: {main.ENABLE_SQUEEZE}"
    assert main.INDEX_SYMBOL == "^NSEI", f"INDEX_SYMBOL changed: {main.INDEX_SYMBOL}"
