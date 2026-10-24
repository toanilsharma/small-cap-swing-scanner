"""
fetch_nse_deals.py
Attempts to fetch today's NSE bulk/block prints and delivery% for the trading universe.
Merges fetched data into deals.json keeping ~30 days of history.

FAIL-OPEN GUARANTEE:
On ANY network, HTTP, cookie, or parsing error:
- Leaves prior deals.json intact.
- Sets top-level "deals_stale": True in scan_results.json.
- Logs a clear warning.
- Exits 0 so the GitHub Actions pipeline never crashes or fails.
"""

import datetime
import json
import os
import sys
import urllib.request
import urllib.error

DEALS_FILE = "deals.json"
SCAN_RESULTS_FILE = "scan_results.json"
MAX_HISTORY_DAYS = 30


def mark_deals_stale_in_scan_results():
    if not os.path.exists(SCAN_RESULTS_FILE):
        return
    try:
        with open(SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data["deals_stale"] = True
            with open(SCAN_RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print("[INFO] scan_results.json updated: deals_stale=True")
    except Exception as e:
        print(f"[WARN] Could not update deals_stale in scan_results.json: {e}")


def load_deals() -> dict:
    if not os.path.exists(DEALS_FILE):
        return {}
    try:
        with open(DEALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_deals(deals: dict):
    # Prune dates older than MAX_HISTORY_DAYS
    sorted_dates = sorted(deals.keys())
    if len(sorted_dates) > MAX_HISTORY_DAYS:
        to_remove = sorted_dates[:-MAX_HISTORY_DAYS]
        for d in to_remove:
            deals.pop(d, None)

    with open(DEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(deals, f, indent=2)
    print(f"[SUCCESS] deals.json updated with {len(deals)} dates of institutional data.")


def fetch_nse_deals_data():
    """
    Attempts to pull bulk/block deals from NSE India endpoints with browser headers.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Request bulk deals
    bulk_url = "https://www.nseindia.com/api/snapshot-capital-market-bulk-deals"
    req = urllib.request.Request(bulk_url, headers=headers)
    
    # Fast 5-second timeout to avoid holding up CI
    with urllib.request.urlopen(req, timeout=5) as response:
        if response.status == 200:
            content = response.read().decode("utf-8")
            return json.loads(content)
        raise urllib.error.HTTPError(bulk_url, response.status, "Non-200 status", response.headers, None)


def main_fetch():
    print("[INFO] Attempting to pull NSE bulk/block and delivery data...")
    today_str = datetime.date.today().isoformat()
    existing_deals = load_deals()

    try:
        raw_data = fetch_nse_deals_data()
        
        # Parse deals if returned
        deals_today = existing_deals.get(today_str, {})
        data_list = raw_data.get("data", []) if isinstance(raw_data, dict) else (raw_data if isinstance(raw_data, list) else [])
        
        for item in data_list:
            sym = str(item.get("symbol", "")).upper()
            if not sym:
                continue
            client = item.get("clientName", item.get("acquirer", "INSTITUTION"))
            buy_sell = item.get("buySell", "BUY")
            is_block = "block" in str(item.get("dealType", "")).lower()
            
            entry = deals_today.get(sym, {"delivery_pct": None, "block_print": False, "bulk_print": False, "inst_name": None})
            if is_block:
                entry["block_print"] = True
            else:
                entry["bulk_print"] = True
            entry["inst_name"] = client
            deals_today[sym] = entry

        existing_deals[today_str] = deals_today
        save_deals(existing_deals)

        # Mark deals not stale in scan_results if available
        if os.path.exists(SCAN_RESULTS_FILE):
            try:
                with open(SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                s_data["deals_stale"] = False
                with open(SCAN_RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(s_data, f, indent=2)
            except Exception:
                pass

    except Exception as err:
        print(f"[WARN] Could not fetch NSE institutional deals data: {err}")
        print("[WARN] Failing open: preserving existing deals.json and setting deals_stale=True")
        mark_deals_stale_in_scan_results()

    return 0


if __name__ == "__main__":
    sys.exit(main_fetch())
