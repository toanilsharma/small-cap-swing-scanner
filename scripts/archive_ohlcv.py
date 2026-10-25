#!/usr/bin/env python3
"""
scripts/archive_ohlcv.py - Nightly OHLCV universe archive (SC-5).

Appends each scanned symbol's latest daily bar (date,symbol,open,high,low,close,volume)
to archive/ohlcv_<YYYY-MM>.csv.gz (gzip, monthly, append-or-create, prune nothing).
Fail-open: On any error, logs a warning and exits 0 so it never breaks CI/CD or the scan.
Guarded out of offline pytest runs.
"""

import os
import sys
import datetime
from typing import List, Optional
import pandas as pd

# Add repo root to import main.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ARCHIVE_DIR = "archive"


def get_archive_filepath(target_date: Optional[datetime.date] = None) -> str:
    """Return the monthly archive filepath: archive/ohlcv_<YYYY-MM>.csv.gz."""
    if target_date is None:
        target_date = datetime.date.today()
    month_str = target_date.strftime("%Y-%m")
    return os.path.join(ARCHIVE_DIR, f"ohlcv_{month_str}.csv.gz")


def append_bars_to_archive(new_rows: List[dict], target_date: Optional[datetime.date] = None) -> str:
    """
    Append or create archive/ohlcv_<YYYY-MM>.csv.gz with columns:
    date,symbol,open,high,low,close,volume.
    Deduplicates by (date, symbol) and prunes nothing.
    Returns path to the written archive file.
    """
    if not new_rows:
        return ""

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_path = get_archive_filepath(target_date)

    df_new = pd.DataFrame(new_rows)
    # Ensure correct column ordering
    expected_cols = ["date", "symbol", "open", "high", "low", "close", "volume"]
    for col in expected_cols:
        if col not in df_new.columns:
            df_new[col] = None
    df_new = df_new[expected_cols]

    if os.path.exists(archive_path):
        try:
            df_existing = pd.read_csv(archive_path, compression="gzip")
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        except Exception as read_err:
            print(f"Warning reading existing archive {archive_path}: {read_err}", file=sys.stderr)
            df_combined = df_new
    else:
        df_combined = df_new

    # Deduplicate keeping newest bar
    df_combined["date"] = df_combined["date"].astype(str)
    df_combined["symbol"] = df_combined["symbol"].astype(str)
    df_combined = df_combined.drop_duplicates(subset=["date", "symbol"], keep="last")
    df_combined = df_combined.sort_values(by=["date", "symbol"])

    df_combined.to_csv(archive_path, compression="gzip", index=False)
    return archive_path


def archive_daily_universe(symbols: Optional[List[str]] = None) -> Optional[str]:
    """
    Collect latest bar for each symbol and append to the monthly archive.
    Strictly fail-open: never raises an exception.
    """
    # Guard out of offline pytest
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RUN_ARCHIVE_IN_TEST"):
        print("Archive step skipped in offline pytest environment.")
        return None

    try:
        import main

        if symbols is None:
            symbols = main.get_symbols()

        if not symbols:
            print("No symbols retrieved to archive.")
            return None

        today = datetime.date.today()
        rows = []
        for sym in symbols:
            try:
                df = main.get_history(sym)
                if df is not None and not df.empty:
                    last_row = df.iloc[-1]
                    bar_date = (
                        pd.to_datetime(last_row["Date"]).strftime("%Y-%m-%d")
                        if "Date" in last_row
                        else today.strftime("%Y-%m-%d")
                    )
                    rows.append({
                        "date": bar_date,
                        "symbol": sym,
                        "open": round(float(last_row.get("Open", last_row.get("Close", 0))), 2),
                        "high": round(float(last_row.get("High", last_row.get("Close", 0))), 2),
                        "low": round(float(last_row.get("Low", last_row.get("Close", 0))), 2),
                        "close": round(float(last_row.get("Close", 0)), 2),
                        "volume": round(float(last_row.get("Volume", 0)), 2),
                    })
            except Exception as row_err:
                # Per-symbol fail-open
                continue

        if not rows:
            print("No bars retrieved for archiving.")
            return None

        target_file = append_bars_to_archive(rows, today)
        file_size_bytes = os.path.getsize(target_file) if os.path.exists(target_file) else 0
        print(f"✅ Archived {len(rows)} bars into {target_file} ({file_size_bytes} bytes).")
        return target_file

    except Exception as exc:
        print(f"WARN: OHLCV archiving failed safely: {exc}", file=sys.stderr)
        return None


if __name__ == "__main__":
    archive_daily_universe()
