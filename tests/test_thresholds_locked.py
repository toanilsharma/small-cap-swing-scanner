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
    assert main.VOLUME_SPIKE_MULTIPLIER == 2.0, f"VOLUME_SPIKE_MULTIPLIER changed: {main.VOLUME_SPIKE_MULTIPLIER}"
    assert main.VOLUME_SPIKE_MIN == 2.0, f"VOLUME_SPIKE_MIN changed: {main.VOLUME_SPIKE_MIN}"
    assert main.MAX_STOP_LOSS_PCT == 0.09, f"MAX_STOP_LOSS_PCT changed: {main.MAX_STOP_LOSS_PCT}"
    assert main.ATR_STOP_MULTIPLIER == 2.0, f"ATR_STOP_MULTIPLIER changed: {main.ATR_STOP_MULTIPLIER}"
    assert main.TARGET_R_MULTIPLE == 2.0, f"TARGET_R_MULTIPLE changed: {main.TARGET_R_MULTIPLE}"
    assert main.RISK_PCT == 0.01, f"RISK_PCT changed: {main.RISK_PCT}"
    assert main.CAPITAL == 100000, f"CAPITAL changed: {main.CAPITAL}"
    assert main.SETUP_WINDOW_DAYS == 10, f"SETUP_WINDOW_DAYS changed: {main.SETUP_WINDOW_DAYS}"
    assert main.TIME_STOP_DAYS == 8, f"TIME_STOP_DAYS changed: {main.TIME_STOP_DAYS}"
    assert main.ADV20_MIN_RUPEES == 50000000, f"ADV20_MIN_RUPEES changed: {main.ADV20_MIN_RUPEES}"
    assert main.MAX_POSITION_ADV_PCT == 0.015, f"MAX_POSITION_ADV_PCT changed: {main.MAX_POSITION_ADV_PCT}"
    assert main.WORST_CASE_GAP_PCT == 0.19, f"WORST_CASE_GAP_PCT changed: {main.WORST_CASE_GAP_PCT}"
    assert main.MAX_GAP_LOSS_PCT == 0.025, f"MAX_GAP_LOSS_PCT changed: {main.MAX_GAP_LOSS_PCT}"
    assert main.DEFAULT_CIRCUIT_BAND == 0.10, f"DEFAULT_CIRCUIT_BAND changed: {main.DEFAULT_CIRCUIT_BAND}"
    assert main.CIRCUIT_PROXIMITY_PCT == 0.02, f"CIRCUIT_PROXIMITY_PCT changed: {main.CIRCUIT_PROXIMITY_PCT}"
    assert main.EARNINGS_BLACKOUT_DAYS == 5, f"EARNINGS_BLACKOUT_DAYS changed: {main.EARNINGS_BLACKOUT_DAYS}"
    assert main.MAX_CONCURRENT_SMALLCAP == 4, f"MAX_CONCURRENT_SMALLCAP changed: {main.MAX_CONCURRENT_SMALLCAP}"
    assert main.MAX_TOTAL_HEAT_PCT == 0.05, f"MAX_TOTAL_HEAT_PCT changed: {main.MAX_TOTAL_HEAT_PCT}"
    assert main.DAILY_STOP_PCT == 0.02, f"DAILY_STOP_PCT changed: {main.DAILY_STOP_PCT}"
    assert main.MONTHLY_STOP_PCT == 0.06, f"MONTHLY_STOP_PCT changed: {main.MONTHLY_STOP_PCT}"


def test_core_flags_and_index_symbol():
    """
    Assert that setup enablement flags, basket parameters, and index symbol remain locked.
    """
    assert main.ENABLE_PULLBACK is False, f"ENABLE_PULLBACK changed: {main.ENABLE_PULLBACK}"
    assert main.ENABLE_SQUEEZE is True, f"ENABLE_SQUEEZE changed: {main.ENABLE_SQUEEZE}"
    assert main.USE_LARGE_CAP_CRASH_CHECK is False, f"USE_LARGE_CAP_CRASH_CHECK changed: {main.USE_LARGE_CAP_CRASH_CHECK}"
    assert main.BASKET_MIN_SYMBOLS_PCT == 0.80, f"BASKET_MIN_SYMBOLS_PCT changed: {main.BASKET_MIN_SYMBOLS_PCT}"
    assert main.BASKET_DRAWDOWN_GUARD_PCT == -0.07, f"BASKET_DRAWDOWN_GUARD_PCT changed: {main.BASKET_DRAWDOWN_GUARD_PCT}"
    assert main.INDEX_SYMBOL == "^NSEI", f"INDEX_SYMBOL changed: {main.INDEX_SYMBOL}"
