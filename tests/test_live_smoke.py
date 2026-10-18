"""
Optional live network smoke test.
Only executed when running: python audit.py --live (or pytest -m live).
Skipped by default in offline audit runs.
"""

from typing import Any
import json
import os
import pytest
import main


@pytest.mark.live
def test_live_network_scan_smoke(tmp_cwd: Any, spy_posts: list, monkeypatch: pytest.MonkeyPatch):
    """
    Real network smoke: calls real get_symbols() and scans the first 2 constituents
    with QUIET="1" and SKIP_GIT_PUSH="1".
    Asserts scan_results.json is published cleanly and NO Telegram calls are dispatched.
    """
    monkeypatch.setenv("QUIET", "1")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")
    monkeypatch.setattr(main, "TELEGRAM_BOT_TOKEN", "123456:mock-token")
    monkeypatch.setattr(main, "TELEGRAM_CHAT_ID", "987654321")

    # Fetch real symbols
    real_symbols = main.get_symbols()
    assert len(real_symbols) > 0, "Real get_symbols() should return constituents"

    # Limit to top 2 to keep smoke test under ~15s
    sample = real_symbols[:2]
    monkeypatch.setattr(main, "get_symbols", lambda: sample)

    signals, count, mkt_ok = main.run_scanner()
    watchlist = main.get_watchlist_candidates()

    now_str = main.get_now_ist().isoformat()
    scan_data = {
        "updated_at": now_str,
        "market_ok": mkt_ok,
        "signals": signals,
        "watchlist": watchlist,
        "scanned_count": count,
    }
    with open(main.SCAN_RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(scan_data, f, indent=2)

    assert os.path.exists(main.SCAN_RESULTS_FILE)
    assert len(spy_posts) == 0, "Zero Telegram calls must be made during quiet live smoke"
