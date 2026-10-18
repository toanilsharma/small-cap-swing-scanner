"""
Shared pytest fixtures and test spies for Midcap Swing Trading Scanner audit harness.
Enforces strict hermetic execution: zero live network calls, zero Telegram messages,
zero mutations to production data files.
"""

import datetime
import time
from typing import Any, Dict, List, Tuple
import pytest
import requests
import main


class FakeTelegramResponse:
    def __init__(self, status_code: int = 200, json_data: Dict[str, Any] = None):
        self.status_code = status_code
        self._json_data = json_data or {"ok": True, "result": {}}
        self.text = '{"ok": true}'

    def json(self) -> Dict[str, Any]:
        return self._json_data

    def raise_for_status(self) -> None:
        pass


@pytest.fixture
def spy_posts(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Recording spy replacing requests.post.
    Records (url, json_payload) and returns a fake HTTP 200 response.
    Never hits external network or real Telegram API.
    """
    recorded: List[Tuple[str, Dict[str, Any]]] = []

    def fake_post(url: str, *args: Any, **kwargs: Any) -> FakeTelegramResponse:
        payload = kwargs.get("json") or kwargs.get("data")
        recorded.append((url, payload))
        return FakeTelegramResponse(200, {"ok": True})

    monkeypatch.setattr(requests, "post", fake_post)
    return recorded


@pytest.fixture
def tmp_cwd(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """
    Hermetic temporary working directory.
    Redirects all file I/O to tmp_path so repo files remain untouched.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def pin_ist_time(monkeypatch: pytest.MonkeyPatch):
    """
    Deterministically pin main.get_now_ist() to any specified IST datetime.
    Can accept datetime object or "HH:MM" / "YYYY-MM-DD HH:MM" string.
    """
    def _pin(time_spec: Any) -> datetime.datetime:
        if isinstance(time_spec, datetime.datetime):
            target_dt = time_spec
            if target_dt.tzinfo is None:
                target_dt = target_dt.replace(tzinfo=main.IST_TZ)
        elif isinstance(time_spec, str):
            time_spec = time_spec.strip()
            if len(time_spec) == 5 and ":" in time_spec:
                h, m = map(int, time_spec.split(":"))
                target_dt = datetime.datetime(2026, 10, 18, h, m, 0, tzinfo=main.IST_TZ)
            else:
                target_dt = datetime.datetime.fromisoformat(time_spec)
                if target_dt.tzinfo is None:
                    target_dt = target_dt.replace(tzinfo=main.IST_TZ)
        else:
            raise ValueError(f"Unsupported time_spec: {time_spec}")

        monkeypatch.setattr(main, "get_now_ist", lambda: target_dt)
        return target_dt

    return _pin


@pytest.fixture(autouse=True)
def hermetic_scan_environment(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """
    Global hermetic environment for all offline tests:
    - Bypasses time.sleep for instantaneous execution.
    - Sets mock Telegram token & chat ID.
    - Sets SKIP_GIT_PUSH=1.
    - Provides a 2-symbol universe ["AAA.NS", "BBB.NS"] with synthetic data.
    - Ensures 50-day turnover > 20 Crores for AAA.NS.
    - Guards requests.get against accidental external network calls.
    """
    if "live" in request.keywords:
        return

    # Fast execution: mock time.sleep
    monkeypatch.setattr(time, "sleep", lambda s: None)

    # Safe mock Telegram credentials
    monkeypatch.setattr(main, "TELEGRAM_BOT_TOKEN", "123456789:ABCDEF-mock-token")
    monkeypatch.setattr(main, "TELEGRAM_CHAT_ID", "987654321")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:ABCDEF-mock-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")

    # Fixed 2-symbol universe
    monkeypatch.setattr(main, "get_symbols", lambda: ["AAA.NS", "BBB.NS"])

    # Build deterministic scenario dataframes
    from tests.test_rules_golden import build_scenario_dataframe
    tb_frame = build_scenario_dataframe("textbook")
    # Scale volume by 2.5 so 50-day turnover (500M) comfortably exceeds MIN_AVG_TURNOVER (200M)
    tb_frame["Volume"] = tb_frame["Volume"] * 2.5
    dt_frame = build_scenario_dataframe("downtrend")

    def mock_get_history(symbol: str):
        if symbol == "AAA.NS":
            return tb_frame.copy()
        elif symbol == "BBB.NS":
            return dt_frame.copy()
        return None

    monkeypatch.setattr(main, "get_history", mock_get_history)
    monkeypatch.setattr(main, "market_ok", lambda: True)
    monkeypatch.setattr(main, "sector_ok", lambda sym: True)
    monkeypatch.setattr(main, "index_return_50", lambda: 0.0)

    # Guard requests.get against unexpected external calls
    def fake_get(url: str, *args: Any, **kwargs: Any):
        if "api.telegram.org" in url:
            return FakeTelegramResponse(200, {"ok": True, "result": []})
        raise RuntimeError(f"Offline hermetic test suite caught unexpected network request to: {url}")

    monkeypatch.setattr(requests, "get", fake_get)
