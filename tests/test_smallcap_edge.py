"""
TEST 9 - tests/test_smallcap_edge.py
Comprehensive unit test suite for the Small-Cap EDGE layer (S3):
1. MOMENTUM RANK cutoff (top MOMENTUM_RANK_TOP=20 eligible, non-eligible blocked).
2. RISING-RS-SLOPE gate (weekly slope >= +2 percentile-points/week required).
3. OBV CONFIRM gate (breakout requires OBV > OBV_HIGH20).
4. SPRING trigger (intraday low < LOW20, close > LOW20, volume >= 1.5x VOL50, stop below spring low).
5. REFINED PULLBACK (pullback to 20-EMA on declining volume reclaimed green, stop below pullback low).
6. CATALYST gate by grade (B-grade requires catalyst or inst print >= 2.5x vol; A/A+ exempt).
7. TAIL-CAPTURE exit asymmetry (+2R 50% partial & breakeven stop, trail 50% on 20-EMA close, 8-day time stop on losers only).
8. Diagnostic keys attached (rs_rating, base_maturity, days_in_base).
"""

import math
import numpy as np
import pandas as pd
import pytest
import main
from tests.test_rules_golden import build_scenario_dataframe


def test_momentum_rank_cutoff(monkeypatch: pytest.MonkeyPatch):
    """
    1) Universe of 25 symbols ranked by volatility-adjusted 6-month return.
    Top 20 symbols are eligible; 21st through 25th are non-eligible.
    """
    symbols = [f"SYM{i:02d}.NS" for i in range(1, 26)]
    monkeypatch.setattr(main, "get_symbols", lambda: symbols)
    main._MOMENTUM_ELIGIBLE_CACHE = None

    history_map = {}
    n = 260
    sine_wave = np.sin(np.linspace(0, 10, 126)) * 0.005
    for i, sym in enumerate(symbols, start=1):
        # SYM01 has highest 126d return (+48%), SYM25 has lowest (+0%)
        ret = 0.50 - (i * 0.02)
        daily_rets = np.concatenate([np.zeros(134), np.full(126, ret / 126.0) + sine_wave])
        close = 100.0 * np.exp(np.cumsum(daily_rets))
        df = pd.DataFrame({
            "Date": pd.date_range("2025-01-01", periods=n, freq="D"),
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.full(n, 1000000.0),
        })
        history_map[sym] = df

    eligible = main.get_momentum_eligible_symbols(symbols=symbols, history_map=history_map)
    assert len(eligible) == main.MOMENTUM_RANK_TOP == 20
    assert "SYM01.NS" in eligible, "Top performing SYM01 must be eligible"
    assert "SYM20.NS" in eligible, "20th symbol must be eligible"
    assert "SYM21.NS" not in eligible, "21st symbol must be blocked by cutoff"
    assert "SYM25.NS" not in eligible, "Bottom symbol must be blocked by cutoff"


def test_rising_rs_slope_gate():
    """
    2) Weekly RS slope: require slope >= +2.0 percentile points / week.
    Accelerating momentum passes; flat or decelerating momentum fails.
    """
    n = 260
    # Accelerating price: +6% in last 3 weeks
    c_acc = np.concatenate([np.full(244, 100.0), np.linspace(100.0, 108.0, 16)])
    df_acc = pd.DataFrame({"Close": c_acc})
    slope_acc = main.calculate_weekly_rs_slope(df_acc)
    assert slope_acc >= 2.0, f"Expected slope >= 2.0, got {slope_acc}"

    # Flat price: slope near 0
    c_flat = np.full(n, 100.0)
    df_flat = pd.DataFrame({"Close": c_flat})
    slope_flat = main.calculate_weekly_rs_slope(df_flat)
    assert slope_flat < 2.0, f"Expected flat slope < 2.0, got {slope_flat}"


def test_obv_confirm_gate():
    """
    3) On a breakout day, OBV must print a new 20-day high.
    If OBV <= OBV_HIGH20, breakout signal is blocked.
    """
    tb = build_scenario_dataframe("textbook")
    tb_res = main.add_indicators(tb)
    assert bool(tb_res.iloc[-1]["OBV_CONFIRM"]) is True
    assert bool(tb_res.iloc[-1]["SIGNAL"]) is True

    rej = build_scenario_dataframe("obv_reject")
    rej_res = main.add_indicators(rej)
    assert bool(rej_res.iloc[-1]["BREAKOUT"]) is True
    assert bool(rej_res.iloc[-1]["VOL_SPIKE"]) is True
    assert bool(rej_res.iloc[-1]["OBV_CONFIRM"]) is False
    assert bool(rej_res.iloc[-1]["SIGNAL"]) is False, "Breakout without OBV confirmation must NOT signal"


def test_spring_trigger(monkeypatch: pytest.MonkeyPatch):
    """
    4) SPRING entry class: price breaks below 20-day low intraday, closes above on >=1.5x vol.
    Initial stop placed below the spring low (tighter than 2.5 ATR default).
    """
    sp_df = build_scenario_dataframe("spring")
    res = main.add_indicators(sp_df)
    last = res.iloc[-1]
    assert bool(last["SPRING"]) is True
    assert bool(last["SIGNAL_SPRING"]) is True
    assert bool(last["BREAKOUT"]) is False

    monkeypatch.setattr(main, "get_history", lambda sym: sp_df)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")

    sig = main.scan_symbol("SPRING.NS")
    assert sig is not None, "Spring setup must emit a valid signal"
    assert sig["Type"] == "SPRING"
    spring_low = float(last["Low"])
    assert sig["Stop"] <= spring_low, f"Spring stop ({sig['Stop']}) must be placed below spring low ({spring_low})"
    expected_spring_stop = max(
        round(min(spring_low - 0.25 * float(last["ATR14"]), float(last["Close"]) - 1.5 * float(last["ATR14"])), 2),
        round(float(last["Close"]) * (1.0 - main.MAX_STOP_LOSS_PCT), 2)
    )
    assert sig["Stop"] == expected_spring_stop, f"Spring stop ({sig['Stop']}) must match adaptive buffer ({expected_spring_stop})"


def test_refined_pullback_trigger(monkeypatch: pytest.MonkeyPatch):
    """
    5) Refined pullback: Stage-2 pullback to 20-EMA on declining volume reclaimed green candle.
    Stop placed below pullback low with 0.25x ATR buffer.
    """
    pb_df = build_scenario_dataframe("pullback")
    res = main.add_indicators(pb_df)
    last = res.iloc[-1]
    assert bool(last["PULLBACK"]) is True
    assert bool(last["SIGNAL_PULLBACK"]) is True
    assert bool(last["BREAKOUT"]) is False

    monkeypatch.setattr(main, "get_history", lambda sym: pb_df)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")

    sig = main.scan_symbol("PULLBACK.NS")
    assert sig is not None, "Pullback setup must emit a valid signal when ENABLE_PULLBACK=True"
    assert sig["Type"] == "PULLBACK"
    pb_low = float(last["Low"])
    assert sig["Stop"] <= pb_low, f"Pullback stop ({sig['Stop']}) must be placed below pullback low ({pb_low})"
    expected_pb_stop = max(
        round(min(pb_low - 0.25 * float(last["ATR14"]), float(last["Close"]) - 1.5 * float(last["ATR14"])), 2),
        round(float(last["Close"]) * (1.0 - main.MAX_STOP_LOSS_PCT), 2)
    )
    assert sig["Stop"] == expected_pb_stop, f"Pullback stop ({sig['Stop']}) must match adaptive buffer ({expected_pb_stop})"


def test_catalyst_gate_by_grade(monkeypatch: pytest.MonkeyPatch):
    """
    6) B-grade signals additionally require an identifiable catalyst OR an institutional print (>=2.5x vol).
    A/A+ grades are exempt.
    """
    tb = build_scenario_dataframe("textbook")
    monkeypatch.setattr(main, "get_history", lambda sym: tb)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")

    # Grade A name passes cleanly
    monkeypatch.setattr(main, "diagnose", lambda sym: {"grade": "A", "score": 75})
    sig_a = main.scan_symbol("GRADEA.NS")
    assert sig_a is not None, "Grade A is exempt from catalyst requirement"

    # Grade B name with normal volume (<2.5x VOL50) and no catalyst is blocked
    monkeypatch.setattr(main, "diagnose", lambda sym: {"grade": "B", "score": 65})
    tb_mod = tb.copy()
    tb_mod.loc[tb_mod.index[-1], "Volume"] = 1_800_000.0  # ~1.9x VOL50, less than 2.5x
    monkeypatch.setattr(main, "get_history", lambda sym: tb_mod)
    sig_b_blocked = main.scan_symbol("GRADEB.NS")
    assert sig_b_blocked is None, "Grade B without catalyst or institutional print must be suppressed"

    # Grade B name with institutional print (>=2.5x VOL50) passes
    tb_inst = tb.copy()
    tb_inst.loc[tb_inst.index[-1], "Volume"] = 3_000_000.0  # > 3.0x VOL50
    monkeypatch.setattr(main, "get_history", lambda sym: tb_inst)
    sig_b_passed = main.scan_symbol("GRADEB.NS")
    assert sig_b_passed is not None, "Grade B with institutional volume print (>=2.5x) must pass"


def test_tail_capture_exit_asymmetry():
    """
    7) Tail-capture exit asymmetry:
    - At +2R: take 50% partial and move stop to breakeven.
    - Trail remaining 50% on 20-EMA close (Close < EMA20).
    - 8-day time stop applies ONLY to positions not in profit; winners ride the trail.
    """
    entry = 100.0
    initial_stop = 92.0  # R = 8.0, Target 2R = 116.0
    ema20 = 110.0

    # 1. Below 2R: hold position
    res1 = main.calculate_tail_capture_exit(
        entry_price=entry,
        current_close=112.0,
        current_low=110.0,
        initial_stop=initial_stop,
        holding_days=5,
        ema20=ema20,
        partial_taken=False,
    )
    assert res1["exit_type"] is None
    assert res1["exit_qty_pct"] == 0.0

    # 2. Reached +2R (116.0): take 50% partial and move stop to breakeven
    res2 = main.calculate_tail_capture_exit(
        entry_price=entry,
        current_close=116.5,
        current_low=114.0,
        initial_stop=initial_stop,
        holding_days=6,
        ema20=ema20,
        partial_taken=False,
    )
    assert res2["exit_type"] == "PARTIAL_2R"
    assert res2["exit_qty_pct"] == 0.50
    assert res2["new_stop"] in (entry, round(entry * (1.0 + getattr(main, "FEE_BUFFER_PCT", 0.0035)), 2)), "Stop must move to breakeven entry price (+ fee buffer)"

    # 3. Post-partial: price above 20-EMA (Close 112 > EMA20 110) -> runner continues riding
    res3 = main.calculate_tail_capture_exit(
        entry_price=entry,
        current_close=112.0,
        current_low=111.0,
        initial_stop=initial_stop,
        holding_days=10,
        ema20=ema20,
        partial_taken=True,
    )
    assert res3["exit_type"] is None, "Winner rides trail above 20-EMA"

    # 4. Post-partial: Close drops below 20-EMA (Close 108 < EMA20 110) -> trail exit
    res4 = main.calculate_tail_capture_exit(
        entry_price=entry,
        current_close=108.0,
        current_low=107.0,
        initial_stop=initial_stop,
        holding_days=12,
        ema20=ema20,
        partial_taken=True,
    )
    assert res4["exit_type"] == "EMA20_TRAIL"
    assert res4["exit_qty_pct"] == 1.0

    # 5. 8-day time stop on losing position (holding_days=8, close 97 <= entry 100) -> time stop cuts loser
    res5 = main.calculate_tail_capture_exit(
        entry_price=entry,
        current_close=97.0,
        current_low=95.0,
        initial_stop=initial_stop,
        holding_days=8,
        ema20=98.0,
        partial_taken=False,
    )
    assert res5["exit_type"] == "TIME_STOP"

    # 6. 8-day time stop on winning position (holding_days=9, close 105 > entry 100) -> NOT stopped by time
    res6 = main.calculate_tail_capture_exit(
        entry_price=entry,
        current_close=105.0,
        current_low=103.0,
        initial_stop=initial_stop,
        holding_days=9,
        ema20=101.0,
        partial_taken=False,
    )
    assert res6["exit_type"] is None, "Time stop must NOT cut positions in profit"


def test_diagnostic_keys_attached(monkeypatch: pytest.MonkeyPatch):
    """
    8) rs_rating (1-99 blended, None if universe < 30), base_maturity (1-4), days_in_base
    must be attached to every signal and watchlist dict.
    """
    tb = build_scenario_dataframe("textbook")
    monkeypatch.setattr(main, "get_history", lambda sym: tb)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")
    monkeypatch.setattr(main, "get_symbols", lambda: ["AAA.NS", "BBB.NS"])  # Universe < 30

    sig = main.scan_symbol("AAA.NS")
    assert sig is not None
    assert "rs_rating" in sig
    assert sig["rs_rating"] is None, "Universe < 30 must yield rs_rating None"
    assert "base_maturity" in sig
    assert 1 <= sig["base_maturity"] <= 4
    assert "days_in_base" in sig
    assert sig["days_in_base"] >= 1

    wl = main.diagnose("AAA.NS")
    assert wl is not None
    assert "rs_rating" in wl
    assert wl["rs_rating"] is None
    assert "base_maturity" in wl
    assert 1 <= wl["base_maturity"] <= 4
    assert "days_in_base" in wl
    assert wl["days_in_base"] >= 1

    # Large universe >= 30 yields 1-99 rs_rating
    universe_35 = [f"STOCK{i:02d}.NS" for i in range(1, 36)]
    monkeypatch.setattr(main, "get_symbols", lambda: universe_35)
    ratings = main.calculate_rs_rating(symbols=universe_35, history_map={s: tb for s in universe_35})
    assert len(ratings) == 35
    for s, r in ratings.items():
        assert r is not None
        assert 1 <= r <= 99


def test_hurst_breakout_gate(monkeypatch: pytest.MonkeyPatch):
    """
    9) Hurst persistence gate:
    - BREAKOUT signals require hurst >= HURST_GATE (0.50).
    - If hurst < HURST_GATE (e.g. 0.42 choppy mean-reverting), BREAKOUT is rejected.
    - If history < 100 bars (hurst is None), fail-open: BREAKOUT is NOT blocked.
    """
    tb = build_scenario_dataframe("textbook")
    monkeypatch.setattr(main, "get_history", lambda sym: tb)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")
    monkeypatch.setattr(main, "diagnose", lambda sym: {"grade": "A", "score": 85})

    # High Hurst (trending, textbook = 0.798) passes
    sig_pass = main.scan_symbol("TB_PASS.NS")
    assert sig_pass is not None, "Textbook breakout with H >= 0.50 must emit signal"
    assert sig_pass["Type"] == "BREAKOUT"

    # Choppy Hurst (H < 0.50) is rejected
    monkeypatch.setattr(main, "calculate_hurst_exponent", lambda df: 0.42)
    sig_rej = main.scan_symbol("CHOPPY_REJ.NS")
    assert sig_rej is None, "Breakout setup with H=0.42 must be suppressed by Hurst gate"

    # Absent Hurst (<100 bars, None) fails open
    monkeypatch.setattr(main, "calculate_hurst_exponent", lambda df: None)
    sig_none = main.scan_symbol("SHORT_HIST.NS")
    assert sig_none is not None, "Breakout with insufficient history (H=None) must fail-open"
    assert sig_none["Type"] == "BREAKOUT"


def test_mean_reversion_setups_ignore_hurst(monkeypatch: pytest.MonkeyPatch):
    """
    Mean-reversion setups (SPRING and PULLBACK) thrive in choppy/rangebound regimes
    and must NEVER be gated or suppressed by low Hurst.
    """
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")
    monkeypatch.setattr(main, "diagnose", lambda sym: {"grade": "A", "score": 85})
    # Force low/choppy Hurst (e.g. 0.35)
    monkeypatch.setattr(main, "calculate_hurst_exponent", lambda df: 0.35)

    # 1. Spring setup with H=0.35 must still pass
    sp_df = build_scenario_dataframe("spring")
    monkeypatch.setattr(main, "get_history", lambda sym: sp_df)
    sig_spring = main.scan_symbol("SPRING_CHOP.NS")
    assert sig_spring is not None, "Spring setup must NOT be blocked by low Hurst"
    assert sig_spring["Type"] == "SPRING"

    # 2. Pullback setup with H=0.35 must still pass
    pb_df = build_scenario_dataframe("pullback")
    monkeypatch.setattr(main, "get_history", lambda sym: pb_df)
    sig_pb = main.scan_symbol("PULLBACK_CHOP.NS")
    assert sig_pb is not None, "Pullback setup must NOT be blocked by low Hurst"
    assert sig_pb["Type"] == "PULLBACK"


def test_ofi_composite_breakout_gate(monkeypatch: pytest.MonkeyPatch):
    """
    10) OFI Composite Breakout Gate:
    - BREAKOUT volume integrity requires: OBV > OBV_HIGH20 AND rolling CMF20 >= OFI_GATE (0.05).
    - If CMF20 < OFI_GATE (e.g. -0.05 sell-side clustering), breakout signal is rejected.
    - If CMF20 is None (<20 bars history), fails open to OBV-only.
    """
    tb = build_scenario_dataframe("textbook")
    monkeypatch.setattr(main, "get_history", lambda sym: tb.copy())
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")
    monkeypatch.setattr(main, "diagnose", lambda sym: {"grade": "A", "score": 85})

    # 1. OBV new high AND rolling CMF20 >= 0.05 passes
    sig_pass = main.scan_symbol("OFI_PASS.NS")
    assert sig_pass is not None, "Breakout with OBV new high and CMF20 >= 0.05 must emit signal"
    assert sig_pass["Type"] == "BREAKOUT"

    # 2. OBV new high but CMF20 < 0.05 (sell-side clustering) is rejected
    tb_neg = tb.copy()
    tb_neg.loc[tb_neg.index[-20:-1], "Close"] = tb_neg.loc[tb_neg.index[-20:-1], "Low"]
    tb_neg_res = main.add_indicators(tb_neg.copy())
    assert bool(tb_neg_res.iloc[-1]["OBV_CONFIRM"]) is False, "OBV_CONFIRM must be False when CMF20 < 0.05"
    monkeypatch.setattr(main, "get_history", lambda sym: tb_neg.copy())
    sig_rej = main.scan_symbol("OFI_REJ.NS")
    assert sig_rej is None, "Breakout with negative CMF20 must be rejected (sell-side clustering)"

    # 3. Absent CMF20 (<20 bars, NaN) fails open to OBV-only
    tb_short = tb.tail(15).copy()
    tb_none = main.add_indicators(tb_short.copy())
    assert bool(tb_none.iloc[-1]["OBV_CONFIRM"]) == bool(tb_none.iloc[-1]["OBV"] > tb_none.iloc[-1]["OBV_HIGH20"]), "OBV_CONFIRM must fail-open to OBV-only when CMF20 is NaN"


def test_mean_reversion_setups_ignore_ofi(monkeypatch: pytest.MonkeyPatch):
    """
    Mean-reversion setups (SPRING and PULLBACK) must NEVER be gated or suppressed
    by CMF20 sell-side clustering.
    """
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")
    monkeypatch.setattr(main, "diagnose", lambda sym: {"grade": "A", "score": 85})

    # 1. Spring setup with sell-side clustering must still pass
    sp_df = build_scenario_dataframe("spring")
    sp_df.loc[sp_df.index[-20:-1], "Close"] = sp_df.loc[sp_df.index[-20:-1], "Low"]
    monkeypatch.setattr(main, "get_history", lambda sym: sp_df)
    sig_spring = main.scan_symbol("SPRING_OFI.NS")
    assert sig_spring is not None, "Spring setup must NOT be blocked by low CMF20"
    assert sig_spring["Type"] == "SPRING"

    # 2. Pullback setup with sell-side clustering must still pass
    pb_df = build_scenario_dataframe("pullback")
    pb_df.loc[pb_df.index[-20:-1], "Close"] = pb_df.loc[pb_df.index[-20:-1], "Low"]
    monkeypatch.setattr(main, "get_history", lambda sym: pb_df)
    sig_pb = main.scan_symbol("PULLBACK_OFI.NS")
    assert sig_pb is not None, "Pullback setup must NOT be blocked by low CMF20"
    assert sig_pb["Type"] == "PULLBACK"


def test_top_momentum_and_rs_rating_gates(monkeypatch: pytest.MonkeyPatch):
    """
    Validates cross-sectional top 25% momentum and RS rating >= 75 gates in scan_symbol.
    """
    tb = build_scenario_dataframe("textbook")
    monkeypatch.setattr(main, "get_history", lambda sym: tb.copy())
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)
    monkeypatch.setattr(main, "get_next_earnings", lambda sym: "2026-12-01")
    monkeypatch.setattr(main, "diagnose", lambda sym, rs_rating=None: {"grade": "A", "score": 85})

    # 1. Symbol NOT in momentum_eligible set is rejected
    sig_not_mom = main.scan_symbol("SYM1.NS", rs_rating=85, momentum_eligible={"LEADER1.NS", "LEADER2.NS"})
    assert sig_not_mom is None, "Symbol outside top-momentum set must be rejected"

    # 2. Symbol in momentum_eligible set but rs_rating < 75 is rejected
    sig_low_rs = main.scan_symbol("SYM1.NS", rs_rating=68, momentum_eligible={"SYM1.NS", "LEADER2.NS"})
    assert sig_low_rs is None, "Symbol with rs_rating < 75 must be rejected"

    # 3. Symbol in momentum_eligible set with rs_rating >= 75 passes
    sig_pass = main.scan_symbol("SYM1.NS", rs_rating=82, momentum_eligible={"SYM1.NS", "LEADER2.NS"})
    assert sig_pass is not None, "Symbol with top-momentum and rs_rating >= 75 must pass"
    assert sig_pass["rs_rating"] == 82


def test_multiscale_hurst_exponent():
    """
    Test multi-scale Hurst exponent calculation on rolling 100-bar returns:
    - Synthetic random walks (independent normal increments) must score near 0.50 ± 0.08 on average.
    - Persistent trends (strong AR(1) positive autocorrelation) must score > 0.60.
    """
    np.random.seed(42)
    rw_scores = []
    for _ in range(50):
        increments = np.random.normal(0, 0.01, 100)
        prices = 100.0 * np.exp(np.cumsum(np.insert(increments, 0, 0.0)))
        df_rw = pd.DataFrame({"Close": prices})
        h = main.calculate_hurst_exponent(df_rw)
        assert h is not None
        rw_scores.append(h)

    mean_rw_h = float(np.mean(rw_scores))
    assert 0.42 <= mean_rw_h <= 0.60, f"Random walk Hurst mean ({mean_rw_h:.3f}) must be near 0.50 ± 0.08"

    trend_scores = []
    for _ in range(50):
        rets = np.zeros(100)
        for t in range(1, 100):
            rets[t] = 0.70 * rets[t-1] + np.random.normal(0, 0.01)
        prices = 100.0 * np.exp(np.cumsum(np.insert(rets, 0, 0.0)))
        df_trend = pd.DataFrame({"Close": prices})
        h = main.calculate_hurst_exponent(df_trend)
        assert h is not None
        trend_scores.append(h)

    mean_trend_h = float(np.mean(trend_scores))
    assert mean_trend_h > 0.60, f"Persistent trend Hurst mean ({mean_trend_h:.3f}) must be > 0.60"

