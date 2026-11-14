"""
tests/test_microstructure_and_delivery.py
Validates NSE-specific market microstructure gates (Rule 18)
and Institutional Delivery Volume Gate (Rule 07 Upgrade).
"""

import pandas as pd
import pytest
import main


def test_rule18_series_filter():
    """Rule 18: Reject Trade-to-Trade BE and BZ series stocks."""
    main._NSE_METADATA_CACHE["TEST_BE"] = {
        "series": "BE",
        "band_pct": 0.20,
        "asm_stage": 0,
        "is_gsm": False,
    }
    ok, reason = main.check_nse_microstructure_gate("TEST_BE")
    assert not ok
    assert "SERIES_RESTRICTED" in reason

    main._NSE_METADATA_CACHE["TEST_BZ"] = {
        "series": "BZ",
        "band_pct": 0.20,
        "asm_stage": 0,
        "is_gsm": False,
    }
    ok, reason = main.check_nse_microstructure_gate("TEST_BZ")
    assert not ok
    assert "SERIES_RESTRICTED" in reason


def test_rule18_surveillance_filter():
    """Rule 18: Reject Long-Term ASM Stage 2, 3, 4 and GSM stocks."""
    # Long-term ASM Stage 2
    main._NSE_METADATA_CACHE["TEST_ASM2"] = {
        "series": "EQ",
        "band_pct": 0.20,
        "asm_stage": 2,
        "is_gsm": False,
    }
    ok, reason = main.check_nse_microstructure_gate("TEST_ASM2")
    assert not ok
    assert "SURVEILLANCE_TRAP" in reason

    # GSM
    main._NSE_METADATA_CACHE["TEST_GSM"] = {
        "series": "EQ",
        "band_pct": 0.20,
        "asm_stage": 0,
        "is_gsm": True,
    }
    ok, reason = main.check_nse_microstructure_gate("TEST_GSM")
    assert not ok
    assert "SURVEILLANCE_TRAP" in reason


def test_rule18_circuit_band_filter():
    """Rule 18: Strictly reject stocks with daily circuit band < 10% (2% and 5%)."""
    # 5% band
    main._NSE_METADATA_CACHE["TEST_BAND5"] = {
        "series": "EQ",
        "band_pct": 0.05,
        "asm_stage": 0,
        "is_gsm": False,
    }
    ok, reason = main.check_nse_microstructure_gate("TEST_BAND5")
    assert not ok
    assert "CIRCUIT_BAND_RESTRICTED" in reason

    # 2% band
    main._NSE_METADATA_CACHE["TEST_BAND2"] = {
        "series": "EQ",
        "band_pct": 0.02,
        "asm_stage": 0,
        "is_gsm": False,
    }
    ok, reason = main.check_nse_microstructure_gate("TEST_BAND2")
    assert not ok
    assert "CIRCUIT_BAND_RESTRICTED" in reason

    # Normal 10% / 20% band
    main._NSE_METADATA_CACHE["TEST_BAND20"] = {
        "series": "EQ",
        "band_pct": 0.20,
        "asm_stage": 0,
        "is_gsm": False,
    }
    ok, reason = main.check_nse_microstructure_gate("TEST_BAND20")
    assert ok


def test_rule07_delivery_gate_confirmed():
    """Rule 07 Upgrade: Confirmed when Delivery_Pct >= 35% or Breakout_Delivery_Vol >= 1.5x 20d avg."""
    df = pd.DataFrame({"Volume": [100000], "VOL20": [50000]})

    # High delivery %
    main._DELIVERY_DATA_CACHE["TEST_DELIV_HIGH"] = {
        "delivery_pct": 38.5,
        "delivery_vol": 38500,
        "avg_delivery_vol_20d": 30000,
        "data_available": True,
    }
    ok, info, reason = main.check_delivery_volume_gate("TEST_DELIV_HIGH", df)
    assert ok
    assert "CONFIRMED" in reason

    # High delivery volume (1.8x avg) even if % is 28%
    main._DELIVERY_DATA_CACHE["TEST_DELIV_VOL"] = {
        "delivery_pct": 28.0,
        "delivery_vol": 45000,
        "avg_delivery_vol_20d": 25000,
        "data_available": True,
    }
    ok, info, reason = main.check_delivery_volume_gate("TEST_DELIV_VOL", df)
    assert ok
    assert "CONFIRMED" in reason


def test_rule07_delivery_gate_rejected():
    """Rule 07 Upgrade: Reject when delivery% < 35% and delivery volume < 1.5x avg."""
    df = pd.DataFrame({"Volume": [100000], "VOL20": [50000]})
    main._DELIVERY_DATA_CACHE["TEST_DELIV_LOW"] = {
        "delivery_pct": 18.0,
        "delivery_vol": 18000,
        "avg_delivery_vol_20d": 25000,
        "data_available": True,
    }
    ok, info, reason = main.check_delivery_volume_gate("TEST_DELIV_LOW", df)
    assert not ok
    assert "DELIVERY_GATE_REJECTED" in reason


def test_rule07_delivery_gate_fallback_when_unavailable():
    """Rule 07 Upgrade: Fall back gracefully to CMF20 + OBV when NSE data is missing/blocked."""
    df = pd.DataFrame({"Volume": [100000], "VOL20": [50000]})
    main._DELIVERY_DATA_CACHE["TEST_DELIV_NONE"] = {
        "delivery_pct": None,
        "delivery_vol": 0.0,
        "avg_delivery_vol_20d": 0.0,
        "data_available": False,
    }
    ok, info, reason = main.check_delivery_volume_gate("TEST_DELIV_NONE", df)
    assert ok
    assert "FALLBACK_CMF20_OBV" in reason

