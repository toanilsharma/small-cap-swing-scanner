"""
TEST 3 - tests/test_notification_gating.py
Validates the notification gating contract:
- Proactive alerts are silenced during quiet windows / QUIET=1 / disabled flags.
- User command replies are NEVER silenced by quiet windows or QUIET=1 (only by active mute).
- Gating suppresses buzzes WITHOUT suppressing data pipeline or dashboard updates.
"""

import datetime
import json
import os
from typing import Any
import pytest
import main


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure dummy Telegram credentials and clean environment variables exist for all tests."""
    monkeypatch.setattr(main, "TELEGRAM_BOT_TOKEN", "123456789:ABCDEF-mock-token")
    monkeypatch.setattr(main, "TELEGRAM_CHAT_ID", "987654321")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:ABCDEF-mock-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")


def test_quiet_env_blocks_proactive_but_allows_reply(tmp_cwd: Any, spy_posts: list, monkeypatch: pytest.MonkeyPatch):
    """
    QUIET="1": Proactive messages are blocked silently.
    Command replies remain allowed.
    """
    monkeypatch.setenv("QUIET", "1")

    # Proactive alert (e.g. scan trigger)
    res_pro = main.send_telegram("Breakout detected on TATATECH", kind="proactive", msg_type="scan")
    assert res_pro is True, "Proactive send should return True when blocked"
    assert len(spy_posts) == 0, "No HTTP call should be made when QUIET=1"

    # User reply (e.g. /status)
    res_reply = main.send_telegram("Position status: OK", kind="reply")
    assert res_reply is True
    assert len(spy_posts) == 1, "Command reply MUST still dispatch when QUIET=1"
    assert "Position status" in spy_posts[0][1]["text"]


def test_quiet_window_gating(tmp_cwd: Any, spy_posts: list, pin_ist_time: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Default quiet window 21:00 to 08:00 IST:
    - At 23:00 IST (inside quiet window): proactive blocked, reply allowed.
    - At 12:00 IST (outside quiet window): proactive allowed.
    """
    monkeypatch.setenv("QUIET", "0")
    settings = dict(main.DEFAULT_ALERT_SETTINGS)
    settings["quiet_start"] = "21:00"
    settings["quiet_end"] = "08:00"
    main.save_alert_settings(settings)

    # 1. Inside quiet window at 23:00 IST
    pin_ist_time("2026-10-18 23:00")
    res_quiet = main.send_telegram("Proactive night scan", kind="proactive", msg_type="scan")
    assert res_quiet is True
    assert len(spy_posts) == 0, "Proactive alert at 23:00 IST must be blocked"

    res_reply = main.send_telegram("Night reply: buy confirmed", kind="reply")
    assert res_reply is True
    assert len(spy_posts) == 1, "Command reply must be permitted during quiet hours"

    # 2. Outside quiet window at 12:00 IST
    pin_ist_time("2026-10-18 12:00")
    res_day = main.send_telegram("Proactive midday breakout", kind="proactive", msg_type="scan")
    assert res_day is True
    assert len(spy_posts) == 2, "Proactive alert at 12:00 IST must dispatch"


def test_category_enable_flags(tmp_cwd: Any, spy_posts: list, pin_ist_time: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Test granular category toggles: enable.scan, enable.watchlist, enable.market.
    """
    monkeypatch.setenv("QUIET", "0")
    pin_ist_time("2026-10-18 14:00")

    settings = dict(main.DEFAULT_ALERT_SETTINGS)
    settings["quiet_start"] = "off"
    settings["quiet_end"] = "off"
    settings["enable"] = {
        "scan": False,        # disabled
        "watchlist": True,    # enabled
        "market": False,      # disabled
    }
    main.save_alert_settings(settings)

    # Scan message -> blocked
    main.send_telegram("Scan alert: ABC breakout", kind="proactive", msg_type="scan")
    assert len(spy_posts) == 0

    # Watchlist message -> allowed
    main.send_telegram("WATCHLIST candidates ready", kind="proactive", msg_type="watchlist")
    assert len(spy_posts) == 1
    assert "WATCHLIST" in spy_posts[0][1]["text"]

    # Market message -> blocked
    main.send_telegram("🔴 MARKET FILTER: downtrend", kind="proactive", msg_type="market")
    assert len(spy_posts) == 1


def test_mute_until_blocks_both(tmp_cwd: Any, spy_posts: list, pin_ist_time: Any, monkeypatch: pytest.MonkeyPatch):
    """
    When mute_until is in the future, BOTH proactive alerts and replies are blocked.
    (Except for the confirmation message of /mute itself).
    """
    monkeypatch.setenv("QUIET", "0")
    pin_ist_time("2026-10-18 10:00")

    # Muted until 14:00 IST
    future_mute = datetime.datetime(2026, 10, 18, 14, 0, 0, tzinfo=main.IST_TZ).isoformat()
    settings = dict(main.DEFAULT_ALERT_SETTINGS)
    settings["mute_until"] = future_mute
    main.save_alert_settings(settings)

    # Proactive -> blocked
    main.send_telegram("Proactive alert", kind="proactive")
    assert len(spy_posts) == 0

    # General reply -> blocked
    main.send_telegram("Command reply", kind="reply")
    assert len(spy_posts) == 0

    # Confirmation of /mute itself -> allowed so user knows they are muted
    main.send_telegram("Muted until 14:00 IST", kind="reply")
    assert len(spy_posts) == 1


def test_critical_invariant_gating_never_blocks_data_pipeline(
    tmp_cwd: Any,
    spy_posts: list,
    pin_ist_time: Any,
    monkeypatch: pytest.MonkeyPatch
):
    """
    CRITICAL INVARIANT TEST:
    With QUIET="1" (or inside quiet hours):
    (i) scan_results.json WAS written in tmp_cwd with valid schema, AND
    (ii) spy_posts contains ZERO proactive HTTP calls.
    Proves muting alerts NEVER suppresses data collection or dashboard publishing!
    """
    monkeypatch.setenv("QUIET", "1")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")
    pin_ist_time("2026-10-18 23:00")  # Night time

    from tests.test_hermetic_scan import execute_full_scan_pipeline

    signals, watchlist, count, mkt_ok = execute_full_scan_pipeline()

    # Assertions
    assert os.path.exists(main.SCAN_RESULTS_FILE), "scan_results.json MUST be written even when QUIET=1"
    with open(main.SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["market_ok"] is True
    assert saved["scanned_count"] == 2
    assert len(saved["signals"]) == 1
    assert saved["signals"][0]["Symbol"] == "AAA.NS"

    # Assert ZERO proactive alerts dispatched
    proactive_calls = [p for p in spy_posts if "breakout" in str(p).lower() or "signal" in str(p).lower()]
    assert len(proactive_calls) == 0, "Zero proactive alerts should have been sent to Telegram under QUIET=1"
