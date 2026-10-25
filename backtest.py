#!/usr/bin/env python3
"""
backtest.py - Rules-Replay Backtester for Small-Cap Swing Strategy (SC-5).

Imports and replays the LIVE production rules from main.py (no duplicate logic):
- main.add_indicators(slice_df) for all technical indicators and triggers.
- main.calculate_position_risk_parameters() for sizing, ATR stops, 9% floor, and 2R targets.
- main.calculate_tail_capture_exit() for 2R partial, 20-EMA trail, time stop, and breakeven ratchet.

CLI:
    python backtest.py --start 2024-01-01 --end 2026-10-24 --out backtest_results.json
"""

import argparse
import datetime
import glob
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

# Import live production functions and constants
import main

DEFAULT_START = "2024-01-01"
DEFAULT_OUT = "backtest_results.json"
ARCHIVE_DIR = "archive"


def load_archive_data(
    archive_dir: str = ARCHIVE_DIR,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Load all archive/ohlcv_*.csv.gz files into a dictionary of DataFrames keyed by symbol.
    Each DataFrame is sorted chronologically by Date.
    """
    if not os.path.isdir(archive_dir):
        return {}

    gz_files = sorted(glob.glob(os.path.join(archive_dir, "ohlcv_*.csv.gz")))
    if not gz_files:
        return {}

    all_dfs = []
    for f in gz_files:
        try:
            df_part = pd.read_csv(f, compression="gzip")
            all_dfs.append(df_part)
        except Exception as exc:
            print(f"Warning reading archive file {f}: {exc}", file=sys.stderr)

    if not all_dfs:
        return {}

    combined = pd.concat(all_dfs, ignore_index=True)
    if "date" in combined.columns:
        combined = combined.rename(columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
            "symbol": "Symbol"
        })

    combined["Date"] = pd.to_datetime(combined["Date"])
    combined = combined.drop_duplicates(subset=["Date", "Symbol"]).sort_values("Date")

    if start_date:
        combined = combined[combined["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        combined = combined[combined["Date"] <= pd.to_datetime(end_date)]

    symbol_map: Dict[str, pd.DataFrame] = {}
    for sym, group in combined.groupby("Symbol"):
        symbol_map[str(sym)] = group.sort_values("Date").reset_index(drop=True)

    return symbol_map


def compute_metrics(
    closed_trades: List[Dict[str, Any]],
    equity_curve: List[Dict[str, Any]],
    period_start: str,
    period_end: str,
) -> Dict[str, Any]:
    """
    Calculate summary statistics, by-grade breakdown, by-signal breakdown,
    and small-cap tail-capture metrics.
    """
    total_trades = len(closed_trades)
    if total_trades == 0:
        return {
            "period": {"start": period_start, "end": period_end},
            "trades": [],
            "equity_curve": equity_curve or [{"date": period_start, "value": main.CAPITAL, "drawdown": 0.0}],
            "win_rate": 0.0,
            "avg_win_R": 0.0,
            "avg_loss_R": 0.0,
            "expectancy_R": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "by_grade": {
                "A+": {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0},
                "A": {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0},
                "B": {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0},
                "C": {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0},
            },
            "by_signal_type": {
                "BREAKOUT": {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0},
                "PULLBACK": {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0},
                "SPRING": {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0},
            },
            "tail_capture": {
                "pct_winners_past_2R": 0.0,
                "avg_R_of_tails": 0.0,
                "capped_vs_trailed_delta": 0.0,
            },
        }

    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] <= 0]

    win_rate = round(len(wins) / total_trades, 3)
    avg_win_r = round(float(np.mean([t["r_multiple"] for t in wins])) if wins else 0.0, 2)
    avg_loss_r = round(float(np.mean([t["r_multiple"] for t in losses])) if losses else 0.0, 2)

    all_r = [t["r_multiple"] for t in closed_trades]
    expectancy_r = round(float(np.mean(all_r)), 2)

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    # Max Drawdown from equity curve
    max_dd = 0.0
    for pt in equity_curve:
        dd = float(pt.get("drawdown", 0.0))
        if dd > max_dd:
            max_dd = dd
    max_drawdown_pct = round(max_dd, 2)

    # By-grade metrics
    by_grade: Dict[str, Dict[str, Any]] = {}
    for grade in ["A+", "A", "B", "C"]:
        grp = [t for t in closed_trades if str(t.get("grade", "")).upper() == grade]
        if grp:
            g_wins = [t for t in grp if t["pnl"] > 0]
            g_loss = abs(sum(t["pnl"] for t in grp if t["pnl"] <= 0))
            g_profit = sum(t["pnl"] for t in g_wins)
            g_pf = round(g_profit / g_loss, 2) if g_loss > 0 else (99.0 if g_profit > 0 else 0.0)
            by_grade[grade] = {
                "trades": len(grp),
                "win_rate": round(len(g_wins) / len(grp), 2),
                "profit_factor": g_pf,
                "expectancy_R": round(float(np.mean([t["r_multiple"] for t in grp])), 2),
            }
        else:
            by_grade[grade] = {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0}

    # By-signal-type metrics
    by_signal: Dict[str, Dict[str, Any]] = {}
    for stype in ["BREAKOUT", "PULLBACK", "SPRING"]:
        grp = [t for t in closed_trades if str(t.get("signal_type", "")).upper() == stype]
        if grp:
            s_wins = [t for t in grp if t["pnl"] > 0]
            s_loss = abs(sum(t["pnl"] for t in grp if t["pnl"] <= 0))
            s_profit = sum(t["pnl"] for t in s_wins)
            s_pf = round(s_profit / s_loss, 2) if s_loss > 0 else (99.0 if s_profit > 0 else 0.0)
            by_signal[stype] = {
                "trades": len(grp),
                "win_rate": round(len(s_wins) / len(grp), 2),
                "profit_factor": s_pf,
                "expectancy_R": round(float(np.mean([t["r_multiple"] for t in grp])), 2),
            }
        else:
            by_signal[stype] = {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0}

    # Small-cap tail capture metrics
    tails = [t for t in wins if t["r_multiple"] >= 2.0]
    pct_winners_past_2r = round((len(tails) / max(1, len(wins))) * 100.0, 1) if wins else 0.0
    avg_r_tails = round(float(np.mean([t["r_multiple"] for t in tails])) if tails else 0.0, 2)

    # Capped vs Trailed Delta:
    # If all winners were capped strictly at +2R, each winner earns at most 2 * risk_amount.
    # Trailed actual PnL minus capped PnL gives the net alpha generated by the 20-EMA trail.
    capped_delta = 0.0
    for t in wins:
        risk_amt = float(t.get("risk_amount", 0.0))
        if risk_amt > 0:
            capped_pnl = 2.0 * risk_amt
            if t["pnl"] > capped_pnl:
                capped_delta += (t["pnl"] - capped_pnl)

    return {
        "period": {"start": period_start, "end": period_end},
        "trades": closed_trades,
        "equity_curve": equity_curve,
        "win_rate": win_rate,
        "avg_win_R": avg_win_r,
        "avg_loss_R": avg_loss_r,
        "expectancy_R": expectancy_r,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "by_grade": by_grade,
        "by_signal_type": by_signal,
        "tail_capture": {
            "pct_winners_past_2R": pct_winners_past_2r,
            "avg_R_of_tails": avg_r_tails,
            "capped_vs_trailed_delta": round(capped_delta, 2),
        },
    }


def run_backtest(
    archive_dfs: Optional[Dict[str, pd.DataFrame]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    out_file: Optional[str] = None,
    initial_capital: float = main.CAPITAL,
) -> Dict[str, Any]:
    """
    Day-by-day rules-replay backtester.
    Imports and executes live functions:
      - main.add_indicators(slice_df)
      - main.calculate_position_risk_parameters(...)
      - main.calculate_tail_capture_exit(...)
    """
    if archive_dfs is None:
        archive_dfs = load_archive_data(ARCHIVE_DIR, start_date=start_date, end_date=end_date)

    if not archive_dfs:
        res = compute_metrics([], [], start_date or DEFAULT_START, end_date or datetime.date.today().isoformat())
        if out_file:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2)
        return res

    # Gather and sort all unique trading dates across all symbols
    all_dates = set()
    for sym, df in archive_dfs.items():
        if "Date" in df.columns:
            all_dates.update(df["Date"].dt.strftime("%Y-%m-%d").tolist())
    sorted_dates = sorted(all_dates)

    if not sorted_dates:
        res = compute_metrics([], [], start_date or DEFAULT_START, end_date or datetime.date.today().isoformat())
        if out_file:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2)
        return res

    period_start = start_date or sorted_dates[0]
    period_end = end_date or sorted_dates[-1]

    # Filter dates
    active_dates = [d for d in sorted_dates if (not start_date or d >= start_date) and (not end_date or d <= end_date)]

    open_positions: List[Dict[str, Any]] = []
    closed_trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []

    capital = initial_capital
    peak_equity = capital

    for current_date_str in active_dates:
        current_dt = pd.to_datetime(current_date_str)

        # -------------------------------------------------------------
        # 1. Advance Open Positions using REAL calculate_tail_capture_exit
        # -------------------------------------------------------------
        surviving_positions = []
        for pos in open_positions:
            sym = pos["symbol"]
            sym_df = archive_dfs.get(sym)
            if sym_df is None:
                surviving_positions.append(pos)
                continue

            day_bar = sym_df[sym_df["Date"] == current_dt]
            if day_bar.empty:
                surviving_positions.append(pos)
                continue

            bar = day_bar.iloc[0]
            close_price = float(bar["Close"])
            low_price = float(bar["Low"])
            pos["holding_days"] += 1

            # Compute current 20-EMA over trailing window for symbol
            hist_up_to_today = sym_df[sym_df["Date"] <= current_dt]
            if len(hist_up_to_today) >= 20:
                ema20_series = hist_up_to_today["Close"].ewm(span=20, adjust=False).mean()
                ema20_val = float(ema20_series.iloc[-1])
            else:
                ema20_val = float(hist_up_to_today["Close"].mean())

            # Call LIVE tail-capture exit function
            exit_info = main.calculate_tail_capture_exit(
                entry_price=pos["entry_price"],
                current_close=close_price,
                current_low=low_price,
                initial_stop=pos["initial_stop"],
                holding_days=pos["holding_days"],
                ema20=ema20_val,
                partial_taken=pos["partial_taken"],
                time_stop_days=main.TIME_STOP_DAYS,
            )

            exit_type = exit_info.get("exit_type")

            if exit_type == "PARTIAL_2R" and not pos["partial_taken"]:
                # Take 50% partial at +2R target
                part_qty = pos["qty"] // 2
                pos["remaining_qty"] -= part_qty
                pos["partial_taken"] = True
                pos["current_stop"] = pos["entry_price"]  # Breakeven ratchet
                target_pnl = part_qty * (pos["target"] - pos["entry_price"])
                pos["partial_pnl"] = target_pnl
                capital += (part_qty * pos["target"])
                surviving_positions.append(pos)

            elif exit_type in ("STOP_LOSS", "BREAKEVEN_STOP", "EMA20_TRAIL", "TIME_STOP"):
                # Complete position exit
                if exit_type in ("STOP_LOSS", "BREAKEVEN_STOP"):
                    exit_price = min(pos["current_stop"], close_price)
                else:
                    exit_price = close_price

                rem_qty = pos["remaining_qty"]
                rem_pnl = rem_qty * (exit_price - pos["entry_price"])
                total_pnl = pos["partial_pnl"] + rem_pnl
                capital += (rem_qty * exit_price)

                r_unit = pos["r_unit"]
                r_mult = round(total_pnl / (pos["qty"] * r_unit), 2) if (pos["qty"] * r_unit) > 0 else 0.0

                closed_trades.append({
                    "symbol": sym,
                    "entry_date": pos["entry_date"],
                    "entry_price": pos["entry_price"],
                    "qty": pos["qty"],
                    "initial_stop": pos["initial_stop"],
                    "target": pos["target"],
                    "signal_type": pos["signal_type"],
                    "grade": pos["grade"],
                    "exit_date": current_date_str,
                    "exit_price": round(exit_price, 2),
                    "exit_reason": exit_type,
                    "pnl": round(total_pnl, 2),
                    "r_multiple": r_mult,
                    "holding_days": pos["holding_days"],
                    "risk_amount": pos["risk_amount"],
                })
            else:
                surviving_positions.append(pos)

        open_positions = surviving_positions

        # -------------------------------------------------------------
        # 2. Check for New Entries on day t
        # -------------------------------------------------------------
        if len(open_positions) < main.MAX_CONCURRENT_SMALLCAP:
            for sym, sym_df in archive_dfs.items():
                if len(open_positions) >= main.MAX_CONCURRENT_SMALLCAP:
                    break
                if any(p["symbol"] == sym for p in open_positions):
                    continue

                hist = sym_df[sym_df["Date"] <= current_dt]
                if len(hist) < 55:
                    continue

                # Run REAL live add_indicators over trailing slice
                ind_df = main.add_indicators(hist)
                last_row = ind_df.iloc[-1]

                # Check setup signals
                is_signal = bool(last_row.get("SIGNAL", False))
                is_spring = bool(last_row.get("SIGNAL_SPRING", False))
                is_pullback = bool(main.ENABLE_PULLBACK and last_row.get("SIGNAL_PULLBACK", False))

                if not (is_signal or is_spring or is_pullback):
                    continue

                sig_type = "BREAKOUT" if is_signal else ("SPRING" if is_spring else "PULLBACK")

                # Sizing & stop via REAL calculate_position_risk_parameters
                entry_val = float(last_row["Close"])
                atr_val = float(last_row["ATR14"])
                low_val = float(last_row["Low"]) if "Low" in last_row else entry_val

                risk_params = main.calculate_position_risk_parameters(
                    entry=entry_val,
                    atr=atr_val,
                    signal_type=sig_type,
                    low_price=low_val,
                    capital=capital,
                )
                if not risk_params:
                    continue

                qty = risk_params["Qty"]
                stop_val = risk_params["Stop"]
                target_val = risk_params["Target"]
                risk_amt = risk_params["Risk Amount"]
                r_unit = risk_params["Risk Per Unit"]

                # Total heat check
                current_heat = sum(p["risk_amount"] for p in open_positions)
                if (current_heat + risk_amt) > (main.CAPITAL * main.MAX_TOTAL_HEAT_PCT):
                    continue

                # Check liquidity cap: notional <= 1.5% of ADV20
                if len(hist) >= 20:
                    adv20 = float((hist["Volume"] * hist["Close"]).iloc[-20:].mean())
                    if adv20 < main.ADV20_MIN_RUPEES or (qty * entry_val) > (main.MAX_POSITION_ADV_PCT * adv20):
                        continue

                # Diagnose grade if possible
                grade = "A"
                try:
                    diag = main.diagnose(sym)
                    if diag and "grade" in diag:
                        grade = diag["grade"]
                except Exception:
                    grade = "A"

                # Deduct cash for open position
                capital -= (qty * entry_val)

                open_positions.append({
                    "symbol": sym,
                    "entry_date": current_date_str,
                    "entry_price": entry_val,
                    "qty": qty,
                    "remaining_qty": qty,
                    "initial_stop": stop_val,
                    "current_stop": stop_val,
                    "target": target_val,
                    "signal_type": sig_type,
                    "grade": grade,
                    "holding_days": 0,
                    "partial_taken": False,
                    "partial_pnl": 0.0,
                    "risk_amount": risk_amt,
                    "r_unit": r_unit,
                })

        # -------------------------------------------------------------
        # 3. Mark-to-Market Portfolio Equity for Equity Curve
        # -------------------------------------------------------------
        portfolio_equity = capital
        for pos in open_positions:
            s_df = archive_dfs.get(pos["symbol"])
            c_val = pos["entry_price"]
            if s_df is not None:
                d_row = s_df[s_df["Date"] == current_dt]
                if not d_row.empty:
                    c_val = float(d_row.iloc[0]["Close"])
            portfolio_equity += (pos["remaining_qty"] * c_val)

        if portfolio_equity > peak_equity:
            peak_equity = portfolio_equity

        dd_pct = ((peak_equity - portfolio_equity) / peak_equity * 100.0) if peak_equity > 0 else 0.0

        equity_curve.append({
            "date": current_date_str,
            "value": round(portfolio_equity, 2),
            "drawdown": round(dd_pct, 2),
        })

    results = compute_metrics(closed_trades, equity_curve, period_start, period_end)

    if out_file:
        os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True) if os.path.dirname(out_file) else None
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"✅ Backtest completed. Results emitted to {out_file}.")

    return results


def main_cli():
    parser = argparse.ArgumentParser(description="Rules-Replay Backtest for Small-Cap Swing Strategy")
    parser.add_argument("--start", type=str, default=DEFAULT_START, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--out", type=str, default=DEFAULT_OUT, help="Output JSON path")
    args = parser.parse_args()

    results = run_backtest(start_date=args.start, end_date=args.end, out_file=args.out)
    print(f"Period: {results['period']['start']} to {results['period']['end']}")
    print(f"Total Trades: {len(results['trades'])} | Win Rate: {results['win_rate']*100:.1f}% | Expectancy: {results['expectancy_R']}R")
    print(f"Profit Factor: {results['profit_factor']} | Max Drawdown: {results['max_drawdown_pct']}%")


if __name__ == "__main__":
    main_cli()
