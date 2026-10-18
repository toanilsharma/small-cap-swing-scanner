"""
TEST 4 - tests/test_offset_state.py
Pins the anti-spam Telegram listener state machine and silent baseline rule.
Guarantees that:
1. Lost bookmarks / first runs never re-reply to historical updates (silent baseline).
2. Older and equal update_ids are strictly ignored.
3. Empty updates lists never mutate the bookmark.
"""

from typing import Any, List, Dict
import pytest
import main


def test_offset_none_establishes_silent_baseline():
    """
    When offset is None (first run or missing tg_offset.txt):
    Must return EMPTY new updates list and advance new_offset to max(update_id) + 1.
    This silent baseline prevents re-answering historical messages on serverless restarts.
    """
    raw_updates: List[Dict[str, Any]] = [
        {"update_id": 100, "message": {"text": "/status", "chat": {"id": 123}}},
        {"update_id": 105, "message": {"text": "/buy ABC 100 95", "chat": {"id": 123}}},
        {"update_id": 110, "message": {"text": "/positions", "chat": {"id": 123}}},
    ]

    new_items, new_offset = main.select_new_updates(raw_updates, offset=None)

    assert new_items == [], "Must return empty items list to skip replies during baseline establishment"
    assert new_offset == 111, "new_offset must be highest_id + 1 (110 + 1 = 111)"


def test_offset_valid_filters_older_and_equal_updates():
    """
    When offset is valid (e.g. 105):
    - Updates with update_id <= 105 must be strictly ignored.
    - Only updates with update_id > 105 are returned.
    - new_offset must be max(new_updates ids) + 1.
    """
    raw_updates: List[Dict[str, Any]] = [
        {"update_id": 100, "message": {"text": "/old1"}},   # older -> ignore
        {"update_id": 105, "message": {"text": "/equal"}},  # equal -> ignore
        {"update_id": 108, "message": {"text": "/new1"}},   # new -> process
        {"update_id": 112, "message": {"text": "/new2"}},   # new -> process
    ]

    new_items, new_offset = main.select_new_updates(raw_updates, offset=105)

    assert len(new_items) == 2, "Only updates with id > 105 should be returned"
    assert [u["update_id"] for u in new_items] == [108, 112]
    assert new_offset == 113, "new_offset must be highest of new items + 1 (112 + 1 = 113)"


def test_empty_updates_leaves_offset_unchanged():
    """When Telegram getUpdates returns an empty list, offset must remain unchanged."""
    new_items, new_offset = main.select_new_updates([], offset=150)
    assert new_items == []
    assert new_offset == 150, "Offset should not change when there are no updates"

    # Also test empty with None offset
    new_items_none, new_offset_none = main.select_new_updates([], offset=None)
    assert new_items_none == []
    assert new_offset_none is None


def test_offset_valid_with_no_newer_updates():
    """If all updates returned are older or equal to current offset, return empty and keep offset."""
    raw_updates = [
        {"update_id": 90, "message": {"text": "/old"}},
        {"update_id": 100, "message": {"text": "/current"}},
    ]
    new_items, new_offset = main.select_new_updates(raw_updates, offset=100)
    assert new_items == []
    assert new_offset == 100
