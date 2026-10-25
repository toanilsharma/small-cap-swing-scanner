"""
Daily NIFTY Midcap 100 Swing-Trading Scanner with Telegram Alerts.
Implements momentum trend-following and pullback setups with discipline rules.
"""

import datetime
import io
import json
import logging
import math
import os
import re
import sys
import time
from typing import Optional, Dict, Any, List, Tuple, Set

# Suppress yfinance warning logs (e.g. 'No data found / may be delisted')
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Ensure utf-8 encoding on Windows console for emoji/unicode support
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

# =====================================================================
# 1) SECRETS AND CONFIGURATION
# =====================================================================
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CAPITAL = 200000
RISK_PCT = 0.01
SEND_NO_SIGNAL_MESSAGE = True
SEND_WATCHLIST = True
ATR_STOP_MULTIPLIER = 2.5
TARGET_R_MULTIPLE = 2.0
MAX_STOP_LOSS_PCT = 0.09
VOLUME_SPIKE_MULTIPLIER = 2.0
VOLUME_SPIKE_MIN = 2.0
SETUP_WINDOW_DAYS = 10
INDEX_SYMBOL = "^NSEI"
USE_LARGE_CAP_CRASH_CHECK = False
BASKET_MIN_SYMBOLS_PCT = 0.80
BASKET_DRAWDOWN_GUARD_PCT = -0.07

# Position-aware liquidity
ADV20_MIN_RUPEES = 50000000  # 5 Crores hard sanity floor
MAX_POSITION_ADV_PCT = 0.01  # 1.0% size-aware cap of ADV20

# Gap / circuit survival sizing
WORST_CASE_GAP_PCT = 0.20
MAX_GAP_LOSS_PCT = 0.025
DEFAULT_CIRCUIT_BAND = 0.10
CIRCUIT_PROXIMITY_PCT = 0.02

# Earnings blackout
EARNINGS_BLACKOUT_DAYS = 5

# Portfolio heat & drawdown limits (Elder circuit-breaker)
MAX_CONCURRENT_SMALLCAP = 3
MAX_TOTAL_HEAT_PCT = 0.05
DAILY_STOP_PCT = 0.02
MONTHLY_STOP_PCT = 0.06

# Execution flags
ENABLE_PULLBACK = True
ENABLE_SQUEEZE = True
TIME_STOP_DAYS = 8
MOMENTUM_RANK_TOP = 20
RS_SLOPE_WEEKS = 4

# File paths & sources
SYMBOL_SOURCE_URL = "https://www.niftyindices.com/IndexConstituent/ind_niftysmallcap100list.csv"
SYMBOLS_SMALLCAP_FILE = "symbols_smallcap.txt"
SYMBOLS_FILE = "symbols.txt"
TRADES_FILE = "trades.json"
OPEN_POSITIONS_FILE = "open_positions.json"
TG_OFFSET_FILE = "tg_offset.txt"
ALERT_SETTINGS_FILE = "alert_settings.json"
SCAN_RESULTS_FILE = "scan_results.json"
CIRCUITS_FILE = "circuits.json"
EARNINGS_FILE = "earnings_dates.json"
DEALS_FILE = "deals.json"
EVENTS_FILE = "events.json"

IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

DEFAULT_ALERT_SETTINGS: Dict[str, Any] = {
    "mute_until": None,
    "quiet_start": "21:00",
    "quiet_end": "08:00",
    "enable": {
        "scan": True,
        "watchlist": True,
        "market": True,
    },
    "digest": False,
}

_DIGEST_MESSAGES: List[Tuple[str, str]] = []


def get_now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST_TZ)


def load_alert_settings() -> Dict[str, Any]:
    """
    Load alert settings from alert_settings.json.
    If missing or corrupt, initialize with defaults.
    """
    settings = dict(DEFAULT_ALERT_SETTINGS)
    if os.path.exists(ALERT_SETTINGS_FILE):
        try:
            with open(ALERT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    settings.update(data)
                    if "enable" in data and isinstance(data["enable"], dict):
                        en = dict(DEFAULT_ALERT_SETTINGS["enable"])
                        en.update(data["enable"])
                        settings["enable"] = en
                    return settings
        except Exception as exc:
            print(f"Warning reading {ALERT_SETTINGS_FILE}: {exc}")

    save_alert_settings(settings)
    return settings


def save_alert_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(ALERT_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Error saving {ALERT_SETTINGS_FILE}: {exc}")


def load_tg_offset() -> Optional[int]:
    """
    Read integer offset from tg_offset.txt if it exists and is non-empty.
    Else returns None (treated as unknown).
    """
    if os.path.exists(TG_OFFSET_FILE):
        try:
            with open(TG_OFFSET_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return int(content)
        except Exception as exc:
            print(f"Warning reading {TG_OFFSET_FILE}: {exc}")
    return None


def save_tg_offset(offset: int) -> None:
    try:
        with open(TG_OFFSET_FILE, "w", encoding="utf-8") as f:
            f.write(str(offset))
    except Exception as exc:
        print(f"Error saving {TG_OFFSET_FILE}: {exc}")

# Sector mapping for NIFTY Midcap 100 and key liquid Indian equities
# Uses only verified, live Yahoo Finance sector index symbols to avoid 404 warnings:
# ^CNXIT, ^NSEBANK, ^CNXAUTO, ^CNXPHARMA, ^CNXFMCG, ^CNXMETAL, ^CNXREALTY, ^CNXMEDIA, ^CNXPSUBANK, ^CNXINFRA
# Financials / NBFCs are mapped to ^NSEBANK.
# Unreliable / missing Yahoo indices (Energy, Commodities, Consumption, Services) are mapped directly to ^NSEI.
SECTOR_MAP: Dict[str, str] = {
    # NIFTY IT (^CNXIT)
    "COFORGE.NS": "^CNXIT",
    "MPHASIS.NS": "^CNXIT",
    "OFSS.NS": "^CNXIT",
    "PERSISTENT.NS": "^CNXIT",
    "LTIM.NS": "^CNXIT",
    "LTTS.NS": "^CNXIT",
    "TCS.NS": "^CNXIT",
    "INFY.NS": "^CNXIT",
    "WIPRO.NS": "^CNXIT",
    "HCLTECH.NS": "^CNXIT",
    "TECHM.NS": "^CNXIT",

    # NIFTY Bank (^NSEBANK)
    "AUBANK.NS": "^NSEBANK",
    "FEDERALBNK.NS": "^NSEBANK",
    "IDFCFIRSTB.NS": "^NSEBANK",
    "INDUSINDBK.NS": "^NSEBANK",
    "YESBANK.NS": "^NSEBANK",
    "BANDHANBNK.NS": "^NSEBANK",
    "RBLBANK.NS": "^NSEBANK",
    "HDFCBANK.NS": "^NSEBANK",
    "ICICIBANK.NS": "^NSEBANK",
    "KOTAKBANK.NS": "^NSEBANK",
    "AXISBANK.NS": "^NSEBANK",

    # Financial Services / NBFC / Insurance (using ^NSEBANK as reliable proxy)
    "360ONE.NS": "^NSEBANK",
    "ABCAPITAL.NS": "^NSEBANK",
    "GROWW.NS": "^NSEBANK",
    "ICICIAMC.NS": "^NSEBANK",
    "ICICIGI.NS": "^NSEBANK",
    "IREDA.NS": "^NSEBANK",
    "LICHSGFIN.NS": "^NSEBANK",
    "LICI.NS": "^NSEBANK",
    "LTF.NS": "^NSEBANK",
    "M&MFIN.NS": "^NSEBANK",
    "MCX.NS": "^NSEBANK",
    "MFSL.NS": "^NSEBANK",
    "MOTILALOFS.NS": "^NSEBANK",
    "PAYTM.NS": "^NSEBANK",
    "POLICYBZR.NS": "^NSEBANK",
    "RECLTD.NS": "^NSEBANK",
    "SBICARD.NS": "^NSEBANK",
    "PFC.NS": "^NSEBANK",
    "CHOLAFIN.NS": "^NSEBANK",
    "SHRIRAMFIN.NS": "^NSEBANK",
    "BAJFINANCE.NS": "^NSEBANK",
    "BAJAJFINSV.NS": "^NSEBANK",

    # NIFTY PSU Bank (^CNXPSUBANK)
    "BANKINDIA.NS": "^CNXPSUBANK",
    "INDIANB.NS": "^CNXPSUBANK",
    "MAHABANK.NS": "^CNXPSUBANK",
    "SBIN.NS": "^CNXPSUBANK",
    "CANBK.NS": "^CNXPSUBANK",
    "PNB.NS": "^CNXPSUBANK",
    "UNIONBANK.NS": "^CNXPSUBANK",

    # NIFTY Auto (^CNXAUTO)
    "ASHOKLEY.NS": "^CNXAUTO",
    "BHARATFORG.NS": "^CNXAUTO",
    "EXIDEIND.NS": "^CNXAUTO",
    "HEROMOTOCO.NS": "^CNXAUTO",
    "MRF.NS": "^CNXAUTO",
    "TIINDIA.NS": "^CNXAUTO",
    "TATAMOTORS.NS": "^CNXAUTO",
    "MARUTI.NS": "^CNXAUTO",
    "M&M.NS": "^CNXAUTO",
    "EICHERMOT.NS": "^CNXAUTO",
    "BAJAJ-AUTO.NS": "^CNXAUTO",
    "BALKRISIND.NS": "^CNXAUTO",
    "BOSCHLTD.NS": "^CNXAUTO",
    "TVSMOTOR.NS": "^CNXAUTO",

    # NIFTY Pharma (^CNXPHARMA)
    "AUROPHARMA.NS": "^CNXPHARMA",
    "BIOCON.NS": "^CNXPHARMA",
    "FORTIS.NS": "^CNXPHARMA",
    "GLENMARK.NS": "^CNXPHARMA",
    "LAURUSLABS.NS": "^CNXPHARMA",
    "LUPIN.NS": "^CNXPHARMA",
    "MANKIND.NS": "^CNXPHARMA",
    "SUNPHARMA.NS": "^CNXPHARMA",
    "DRREDDY.NS": "^CNXPHARMA",
    "CIPLA.NS": "^CNXPHARMA",
    "DIVISLAB.NS": "^CNXPHARMA",
    "ALKEM.NS": "^CNXPHARMA",
    "TORNTPHARM.NS": "^CNXPHARMA",
    "ZYDUSLIFE.NS": "^CNXPHARMA",
    "APOLLOHOSP.NS": "^CNXPHARMA",

    # NIFTY FMCG (^CNXFMCG)
    "COLPAL.NS": "^CNXFMCG",
    "DABUR.NS": "^CNXFMCG",
    "GODFRYPHLP.NS": "^CNXFMCG",
    "MARICO.NS": "^CNXFMCG",
    "PATANJALI.NS": "^CNXFMCG",
    "ITC.NS": "^CNXFMCG",
    "HINDUNILVR.NS": "^CNXFMCG",
    "NESTLEIND.NS": "^CNXFMCG",
    "BRITANNIA.NS": "^CNXFMCG",
    "TATACONSUM.NS": "^CNXFMCG",
    "PGHH.NS": "^CNXFMCG",
    "EMAMILTD.NS": "^CNXFMCG",

    # NIFTY Metal (^CNXMETAL)
    "APLAPOLLO.NS": "^CNXMETAL",
    "HINDCOPPER.NS": "^CNXMETAL",
    "NATIONALUM.NS": "^CNXMETAL",
    "NMDC.NS": "^CNXMETAL",
    "SAIL.NS": "^CNXMETAL",
    "TATASTEEL.NS": "^CNXMETAL",
    "JSWSTEEL.NS": "^CNXMETAL",
    "HINDALCO.NS": "^CNXMETAL",
    "JINDALSTEL.NS": "^CNXMETAL",
    "VEDL.NS": "^CNXMETAL",

    # NIFTY Realty (^CNXREALTY)
    "GODREJPROP.NS": "^CNXREALTY",
    "LODHA.NS": "^CNXREALTY",
    "OBEROIRLTY.NS": "^CNXREALTY",
    "PHOENIXLTD.NS": "^CNXREALTY",
    "PRESTIGE.NS": "^CNXREALTY",
    "DLF.NS": "^CNXREALTY",
    "BRIGADE.NS": "^CNXREALTY",

    # NIFTY Infra / Capital Goods (^CNXINFRA)
    "APARINDS.NS": "^CNXINFRA",
    "ASTRAL.NS": "^CNXINFRA",
    "BDL.NS": "^CNXINFRA",
    "BHEL.NS": "^CNXINFRA",
    "COCHINSHIP.NS": "^CNXINFRA",
    "GMRAIRPORT.NS": "^CNXINFRA",
    "GVT&D.NS": "^CNXINFRA",
    "INDUSTOWER.NS": "^CNXINFRA",
    "KEI.NS": "^CNXINFRA",
    "RVNL.NS": "^CNXINFRA",
    "LT.NS": "^CNXINFRA",
    "HAL.NS": "^CNXINFRA",
    "BEL.NS": "^CNXINFRA",
    "ULTRACEMCO.NS": "^CNXINFRA",
    "GRASIM.NS": "^CNXINFRA",

    # NIFTY Media (^CNXMEDIA)
    "SUNTV.NS": "^CNXMEDIA",
    "ZEEL.NS": "^CNXMEDIA",
    "PVRINOX.NS": "^CNXMEDIA",

    # Energy (mapped to ^NSEI due to unreliable Yahoo sector index)
    "ATGL.NS": "^NSEI",
    "HINDPETRO.NS": "^NSEI",
    "JSWENERGY.NS": "^NSEI",
    "NHPC.NS": "^NSEI",
    "NLCINDIA.NS": "^NSEI",
    "OIL.NS": "^NSEI",
    "PREMIERENE.NS": "^NSEI",
    "SUZLON.NS": "^NSEI",
    "WAAREEENER.NS": "^NSEI",
    "RELIANCE.NS": "^NSEI",
    "NTPC.NS": "^NSEI",
    "POWERGRID.NS": "^NSEI",
    "ONGC.NS": "^NSEI",
    "BPCL.NS": "^NSEI",
    "IOC.NS": "^NSEI",
    "TATAPOWER.NS": "^NSEI",
    "ADANIGREEN.NS": "^NSEI",
    "ADANIPOWER.NS": "^NSEI",

    # Commodities (mapped to ^NSEI due to unreliable Yahoo sector index)
    "PIIND.NS": "^NSEI",
    "SRF.NS": "^NSEI",
    "UPL.NS": "^NSEI",
    "DEEPAKNTR.NS": "^NSEI",
    "TATACHEM.NS": "^NSEI",

    # Consumption (mapped to ^NSEI due to unreliable Yahoo sector index)
    "BLUESTARCO.NS": "^NSEI",
    "DIXON.NS": "^NSEI",
    "HAVELLS.NS": "^NSEI",
    "INDHOTEL.NS": "^NSEI",
    "JUBLFOOD.NS": "^NSEI",
    "KALYANKJIL.NS": "^NSEI",
    "LENSKART.NS": "^NSEI",
    "LGEINDIA.NS": "^NSEI",
    "MEESHO.NS": "^NSEI",
    "NYKAA.NS": "^NSEI",
    "PAGEIND.NS": "^NSEI",
    "RADICO.NS": "^NSEI",
    "SUPREMEIND.NS": "^NSEI",
    "SWIGGY.NS": "^NSEI",
    "UNITDSPR.NS": "^NSEI",
    "VMM.NS": "^NSEI",
    "VOLTAS.NS": "^NSEI",
    "TITAN.NS": "^NSEI",
    "TRENT.NS": "^NSEI",
    "ASIANPAINT.NS": "^NSEI",

    # Service Sector (mapped to ^NSEI due to unreliable Yahoo sector index)
    "CONCOR.NS": "^NSEI",
    "IRCTC.NS": "^NSEI",
    "NAUKRI.NS": "^NSEI",
    "TATACOMM.NS": "^NSEI",
    "BHARTIARTL.NS": "^NSEI",
    "INTERGLOBE.NS": "^NSEI",
}

# Cache for the index historical dataframe
_INDEX_CACHE: Optional[pd.DataFrame] = None
# Cache for sector historical dataframes
_SECTOR_CACHE: Dict[str, pd.DataFrame] = {}


# =====================================================================
# 2) TELEGRAM ALERTS
# =====================================================================
def _dispatch_telegram_http(message: str) -> bool:
    """
    Perform actual HTTP POST requests to Telegram sendMessage with chunking.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing from .env")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunk_size = 3500
    all_success = True

    # Split message into chunks if length exceeds chunk_size
    chunks = [message[i : i + chunk_size] for i in range(0, len(message), chunk_size)] if message else [""]

    for idx, chunk in enumerate(chunks, start=1):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
        }
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                print(f"Telegram chunk {idx}/{len(chunks)} sent successfully.")
            else:
                print(f"Telegram Error ({response.status_code}): {response.text}")
                all_success = False
        except Exception as exc:
            print(f"Telegram Exception sending chunk {idx}/{len(chunks)}: {exc}")
            all_success = False

    return all_success


def send_telegram(
    message: str,
    kind: str = "proactive",
    msg_type: Optional[str] = None
) -> bool:
    """
    Send a message to Telegram using bot API with gating rules.
    kind is 'proactive' for scan/watchlist/market/no-signals alerts and 'reply' for user commands.
    A proactive send is blocked silently (print "[BLOCKED:<reason>] <first 40 chars>" and return True) if:
      (a) QUIET environment variable is '1'
      (b) mute_until is active (now < mute_until)
      (c) current IST time is inside quiet_start..quiet_end window
      (d) matching enable flag is false (scan / watchlist / market)
    A 'reply' send is blocked ONLY by (b) mute.
    """
    if not message:
        return True

    # Normalize kind if caller passed msg_type as kind e.g. send_telegram(msg, kind="scan")
    if kind in ("scan", "watchlist", "market"):
        msg_type = kind
        kind = "proactive"

    settings = load_alert_settings()
    now_ist = get_now_ist()

    # Rule (b): Mute check applies to BOTH proactive and reply
    mute_until_val = settings.get("mute_until")
    if mute_until_val:
        try:
            mute_dt = datetime.datetime.fromisoformat(mute_until_val)
            if mute_dt.tzinfo is None:
                mute_dt = mute_dt.replace(tzinfo=IST_TZ)
            if now_ist < mute_dt:
                # Allow the confirmation reply of /mute itself so the user knows they are muted
                if kind == "reply" and message.startswith("Muted until"):
                    pass
                else:
                    first_chars = message[:40].replace("\n", " ")
                    print(f"[BLOCKED:mute] {first_chars}")
                    return True
        except Exception as exc:
            print(f"Warning parsing mute_until: {exc}")

    # Reply is blocked ONLY by (b) mute
    if kind == "reply":
        return _dispatch_telegram_http(message)

    # Gating for proactive alerts:
    # Rule (a): Environment variable QUIET == "1"
    if os.getenv("QUIET", "0").strip() == "1":
        first_chars = message[:40].replace("\n", " ")
        print(f"[BLOCKED:quiet_env] {first_chars}")
        return True

    # Rule (c): Inside quiet window quiet_start..quiet_end (handles past-midnight wrap)
    q_start = settings.get("quiet_start")
    q_end = settings.get("quiet_end")
    if q_start and q_end and q_start != "off" and q_end != "off":
        try:
            qs_h, qs_m = map(int, q_start.split(":"))
            qe_h, qe_m = map(int, q_end.split(":"))
            now_m = now_ist.hour * 60 + now_ist.minute
            start_m = qs_h * 60 + qs_m
            end_m = qe_h * 60 + qe_m

            in_quiet = False
            if start_m < end_m:
                in_quiet = (start_m <= now_m < end_m)
            elif start_m > end_m:
                in_quiet = (now_m >= start_m or now_m < end_m)

            if in_quiet:
                first_chars = message[:40].replace("\n", " ")
                print(f"[BLOCKED:quiet_window] {first_chars}")
                return True
        except Exception as exc:
            print(f"Warning checking quiet window ({q_start}-{q_end}): {exc}")

    # Rule (d): Matching enable flag is false (scan / watchlist / market)
    eff_type = msg_type
    if not eff_type:
        if "MARKET FILTER" in message:
            eff_type = "market"
        elif "WATCHLIST" in message:
            eff_type = "watchlist"
        else:
            eff_type = "scan"

    enable_flags = settings.get("enable", {})
    if not enable_flags.get(eff_type, True):
        first_chars = message[:40].replace("\n", " ")
        print(f"[BLOCKED:disabled_{eff_type}] {first_chars}")
        return True

    return _dispatch_telegram_http(message)



# =====================================================================
# 3) SYMBOL LIST RETRIEVAL
# =====================================================================
def parse_symbols_file(filepath: str) -> List[str]:
    """Parse symbols from a local text file with comments (#) and comma/whitespace delimiters."""
    if not os.path.exists(filepath):
        return []
    symbols: List[str] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = re.split(r"[\s,]+", line)
                for part in parts:
                    if part.startswith("#"):
                        break
                    cleaned = part.strip().upper()
                    if not cleaned:
                        continue
                    if cleaned.endswith(".NS"):
                        cleaned = cleaned[:-3]
                    sym = f"{cleaned}.NS"
                    if sym not in symbols:
                        symbols.append(sym)
    except Exception as exc:
        print(f"Warning reading {filepath}: {exc}")
    return symbols


def get_symbols() -> List[str]:
    """
    Load symbols from symbols_smallcap.txt if available and non-empty.
    Fallback to symbols.txt. If empty or missing, download NIFTY Smallcap 100 constituents
    from SYMBOL_SOURCE_URL. If download fails/404s/blocks, fail gracefully without crashing.
    """
    # 1. Check small-cap manual override file
    symbols = parse_symbols_file(SYMBOLS_SMALLCAP_FILE)
    if symbols:
        return symbols

    # 2. Check legacy symbols.txt
    symbols = parse_symbols_file(SYMBOLS_FILE)
    if symbols:
        return symbols

    # 3. Fallback: Download NIFTY Smallcap 100 constituents from CSV
    print(f"symbols_smallcap.txt is empty or missing. Auto-downloading small-cap constituents from {SYMBOL_SOURCE_URL}...")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,application/csv,*/*",
        "Referer": "https://www.niftyindices.com/",
    }

    try:
        resp = requests.get(SYMBOL_SOURCE_URL, headers=headers, timeout=20)
        if resp.status_code == 200 and resp.text:
            lines = resp.text.splitlines()
            start_line_idx = None
            for idx, line in enumerate(lines):
                if "symbol" in line.lower():
                    start_line_idx = idx
                    break

            if start_line_idx is not None:
                csv_payload = "\n".join(lines[start_line_idx:])
                df_csv = pd.read_csv(io.StringIO(csv_payload))

                # Identify symbol column
                target_col = None
                for col in df_csv.columns:
                    if "symbol" in str(col).lower():
                        target_col = col
                        break

                if target_col is not None:
                    raw_symbols = df_csv[target_col].dropna().astype(str).str.upper().str.strip()
                    for raw_sym in raw_symbols:
                        if raw_sym.endswith(".NS"):
                            raw_sym = raw_sym[:-3]
                        if re.match(r"^[A-Z0-9&.-]+$", raw_sym):
                            sym = f"{raw_sym}.NS"
                            if sym not in symbols:
                                symbols.append(sym)
        else:
            print(f"Notice: CSV URL {SYMBOL_SOURCE_URL} returned HTTP {resp.status_code}.")
            print(f"Instruction: Please populate '{SYMBOLS_SMALLCAP_FILE}' with small-cap symbols (one per line).")
    except Exception as exc:
        print(f"Notice: Could not fetch small-cap list from {SYMBOL_SOURCE_URL}: {exc}")
        print(f"Instruction: Please populate '{SYMBOLS_SMALLCAP_FILE}' with small-cap symbols (one per line).")

    if not symbols:
        print(f"Warning: No small-cap symbols found. Please create and populate '{SYMBOLS_SMALLCAP_FILE}'.")
        return []

    return symbols


# =====================================================================
# 4) HISTORICAL DATA RETRIEVAL
# =====================================================================
_HISTORY_CACHE: Dict[str, pd.DataFrame] = {}


def get_history(symbol: str) -> Optional[pd.DataFrame]:
    """
    Download 2 years of daily historical data for the symbol from Yahoo Finance.
    Returns clean DataFrame with Date, Open, High, Low, Close, Volume.
    """
    global _HISTORY_CACHE
    if symbol in _HISTORY_CACHE:
        return _HISTORY_CACHE[symbol]

    try:
        df = yf.download(symbol, period="2y", interval="1d", auto_adjust=False, progress=False)
        if df is None or df.empty:
            return None

        # Reset index to extract Date
        df = df.reset_index()

        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Rename first column to Date
        df.rename(columns={df.columns[0]: "Date"}, inplace=True)

        # Keep only required columns
        required_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
        for col in required_cols:
            if col not in df.columns:
                return None
        df = df[required_cols].copy()

        # Standardize date and numbers
        df["Date"] = pd.to_datetime(df["Date"])
        if df["Date"].dt.tz is not None:
            df["Date"] = df["Date"].dt.tz_localize(None)
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
        for num_col in ["Open", "High", "Low", "Close"]:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")

        df = df.dropna(subset=["Close"]).reset_index(drop=True)
        if df.empty:
            return None

        _HISTORY_CACHE[symbol] = df
        return df
    except Exception:
        return None


# =====================================================================
# 5) SMALL-CAP EDGE HELPER FUNCTIONS & INDICATORS
# =====================================================================
def calculate_vol_adj_return(df: pd.DataFrame) -> Optional[float]:
    """
    Volatility-adjusted 6-month return:
    ret_126d / (std of daily returns over 126d).
    """
    if df is None or len(df) < 127:
        return None
    c = df["Close"]
    c_now = float(c.iloc[-1])
    c_prev = float(c.iloc[-127])
    if c_prev <= 0 or pd.isna(c_now) or pd.isna(c_prev):
        return None
    ret_126 = (c_now / c_prev) - 1.0
    daily_rets = c.pct_change().iloc[-126:]
    std_126 = float(daily_rets.std())
    if std_126 <= 0 or pd.isna(std_126):
        return None
    return float(ret_126 / std_126)


_MOMENTUM_ELIGIBLE_CACHE: Optional[Tuple[datetime.date, Set[str]]] = None


def get_momentum_eligible_symbols(symbols: Optional[List[str]] = None, history_map: Optional[Dict[str, pd.DataFrame]] = None) -> Set[str]:
    """
    Rank universe by volatility-adjusted 6-month return = ret_126d / (std of daily returns over 126d).
    Only the top MOMENTUM_RANK_TOP=20 symbols are ELIGIBLE for any new entry.
    Ties broken by symbol ascending.
    If universe <= MOMENTUM_RANK_TOP, all symbols with history are eligible.
    """
    global _MOMENTUM_ELIGIBLE_CACHE
    today = datetime.date.today()
    if _MOMENTUM_ELIGIBLE_CACHE is not None and _MOMENTUM_ELIGIBLE_CACHE[0] == today and symbols is None:
        return _MOMENTUM_ELIGIBLE_CACHE[1]

    if symbols is None:
        symbols = get_symbols()
    if not symbols:
        return set()

    if len(symbols) <= MOMENTUM_RANK_TOP:
        eligible = set(symbols)
        _MOMENTUM_ELIGIBLE_CACHE = (today, eligible)
        return eligible

    scores: List[Tuple[float, str]] = []
    for sym in symbols:
        df = history_map.get(sym) if history_map else get_history(sym)
        if df is not None and len(df) >= 127:
            val = calculate_vol_adj_return(df)
            if val is not None and not math.isnan(val):
                scores.append((val, sym))
            else:
                scores.append((-1e9, sym))
        else:
            scores.append((-1e9, sym))

    # Sort descending by score, ascending by symbol for tie breaks
    scores.sort(key=lambda x: (-x[0], x[1]))
    eligible = {sym for _, sym in scores[:MOMENTUM_RANK_TOP]}
    _MOMENTUM_ELIGIBLE_CACHE = (today, eligible)
    return eligible


def calculate_weekly_rs_slope(df_symbol: pd.DataFrame, df_benchmark: Optional[pd.DataFrame] = None) -> float:
    """
    Compute weekly RS slope over the last RS_SLOPE_WEEKS=4 weeks.
    Evaluates 4 weekly closes (t, t-5, t-10, t-15).
    If benchmark is provided, RS = Close_symbol / Close_benchmark.
    Otherwise, evaluates normalized price momentum over the 4 weeks.
    Returns slope in percentile-points / relative-strength points per week.
    """
    if len(df_symbol) < 20:
        return 0.0

    c = df_symbol["Close"]
    indices = [-16, -11, -6, -1]
    
    if df_benchmark is not None and len(df_benchmark) >= 20:
        b = df_benchmark["Close"]
        rs_vals = [(float(c.iloc[idx]) / max(1e-6, float(b.iloc[idx]))) for idx in indices]
        base = rs_vals[0]
        y = [((v / max(1e-6, base)) - 1.0) * 100.0 * 2.5 for v in rs_vals]
    else:
        c_base = float(c.iloc[indices[0]])
        if c_base <= 0:
            return 0.0
        y = [((float(c.iloc[idx]) / c_base) - 1.0) * 100.0 * 2.5 for idx in indices]

    slope = (3.0 * (y[3] - y[0]) + (y[2] - y[1])) / 10.0
    return float(slope)


def calculate_rs_rating(symbols: Optional[List[str]] = None, history_map: Optional[Dict[str, pd.DataFrame]] = None) -> Dict[str, Optional[int]]:
    """
    Blended 1-99 RS rating:
    0.4*ret63 + 0.2*ret126 + 0.2*ret189 + 0.2*ret252.
    Ties broken by symbol ascending.
    Returns None if universe < 30.
    """
    if symbols is None:
        symbols = get_symbols()
    if not symbols or len(symbols) < 30:
        return {sym: None for sym in (symbols or [])}

    scored: List[Tuple[float, str]] = []
    for sym in symbols:
        df = history_map.get(sym) if history_map else get_history(sym)
        if df is not None and len(df) >= 63:
            c = df["Close"]
            c_now = float(c.iloc[-1])
            ret63 = (c_now / float(c.iloc[-64])) - 1.0 if len(c) >= 64 else 0.0
            ret126 = (c_now / float(c.iloc[-127])) - 1.0 if len(c) >= 127 else ret63
            ret189 = (c_now / float(c.iloc[-190])) - 1.0 if len(c) >= 190 else ret126
            ret252 = (c_now / float(c.iloc[-253])) - 1.0 if len(c) >= 253 else ret189
            blended = 0.4 * ret63 + 0.2 * ret126 + 0.2 * ret189 + 0.2 * ret252
            scored.append((blended, sym))
        else:
            scored.append((-1e9, sym))

    scored.sort(key=lambda x: (-x[0], x[1]))
    n = len(scored)
    ratings: Dict[str, Optional[int]] = {}
    for rank, (_, sym) in enumerate(scored):
        pct = 1 + int(round(98.0 * (n - 1 - rank) / max(1, n - 1)))
        ratings[sym] = max(1, min(99, pct))

    return ratings


def calculate_base_maturity(df: pd.DataFrame) -> int:
    """
    Base maturity (1-4): successive step-downs of 10d rolling (H-L)/C std.
    """
    if df is None or len(df) < 40:
        return 1
    safe_close = df["Close"].replace(0, np.nan)
    norm_range = (df["High"] - df["Low"]) / safe_close
    
    s1 = float(norm_range.iloc[-40:-30].std())
    s2 = float(norm_range.iloc[-30:-20].std())
    s3 = float(norm_range.iloc[-20:-10].std())
    s4 = float(norm_range.iloc[-10:].std())

    maturity = 1
    if not math.isnan(s2) and not math.isnan(s1) and s2 < s1:
        maturity = 2
        if not math.isnan(s3) and s3 < s2:
            maturity = 3
            if not math.isnan(s4) and s4 < s3:
                maturity = 4
    return maturity


def calculate_days_in_base(df: pd.DataFrame) -> int:
    """
    Number of consecutive days price has traded in the consolidation base.
    """
    if df is None or len(df) < 20:
        return 1
    high20 = float(df["High"].rolling(20).max().iloc[-1])
    low20 = float(df["Low"].rolling(20).min().iloc[-1])
    if high20 <= 0:
        return 1

    closes = df["Close"].values
    count = 0
    for c in reversed(closes):
        if (c >= low20 * 0.97) and (c <= high20 * 1.03):
            count += 1
        else:
            break
    return max(1, count)


def calculate_tail_capture_exit(
    entry_price: float,
    current_close: float,
    current_low: float,
    initial_stop: float,
    holding_days: int,
    ema20: float,
    partial_taken: bool = False,
    time_stop_days: int = TIME_STOP_DAYS,
) -> Dict[str, Any]:
    """
    Tail-capture exit asymmetry:
    - At +2R: take 50% partial and move stop to breakeven (entry_price).
    - Trail remaining 50%: exit on 20-EMA close (Close < EMA20).
    - 8-day TIME_STOP applies ONLY to positions NOT in profit (Close <= entry_price).
      Winners ride the trail; losers get cut by time.
    """
    r_unit = max(1e-4, entry_price - initial_stop)
    target_2r = entry_price + (2.0 * r_unit)

    effective_stop = entry_price if partial_taken else initial_stop
    if current_low <= effective_stop or current_close < effective_stop:
        return {
            "exit_type": "BREAKEVEN_STOP" if partial_taken else "STOP_LOSS",
            "exit_qty_pct": 1.0,
            "new_stop": effective_stop,
            "partial_taken": partial_taken,
            "reason": f"Hit {'breakeven' if partial_taken else 'initial'} stop (₹{effective_stop:.2f})",
        }

    if not partial_taken and current_close >= target_2r:
        return {
            "exit_type": "PARTIAL_2R",
            "exit_qty_pct": 0.50,
            "new_stop": entry_price,
            "partial_taken": True,
            "reason": f"Hit +2R target (₹{target_2r:.2f}): take 50% partial, stop moved to breakeven",
        }

    if partial_taken and current_close < ema20:
        return {
            "exit_type": "EMA20_TRAIL",
            "exit_qty_pct": 1.0,
            "new_stop": effective_stop,
            "partial_taken": True,
            "reason": f"Close (₹{current_close:.2f}) dropped below 20-EMA (₹{ema20:.2f}): trail exit triggered",
        }

    if holding_days >= time_stop_days:
        if current_close <= entry_price:
            return {
                "exit_type": "TIME_STOP",
                "exit_qty_pct": 1.0,
                "new_stop": effective_stop,
                "partial_taken": partial_taken,
                "reason": f"8-day time stop reached ({holding_days} days) and position not in profit",
            }

    return {
        "exit_type": None,
        "exit_qty_pct": 0.0,
        "new_stop": effective_stop,
        "partial_taken": partial_taken,
        "reason": "Hold position",
    }


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute moving averages, volatility measures, trend filters,
    squeeze detection, edge gates, and setup/trigger signals.
    """
    df = df.copy()

    # Moving averages of Close
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA150"] = df["Close"].rolling(150).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()

    # Moving averages of Volume
    df["VOL5"] = df["Volume"].rolling(5).mean()
    df["VOL50"] = df["Volume"].rolling(50).mean()

    # Range calculations (High - Low)
    hl_range = df["High"] - df["Low"]
    df["RANGE5"] = hl_range.rolling(5).mean()
    df["RANGE50"] = hl_range.rolling(50).mean()

    # True Range & ATR14
    prev_close = df["Close"].shift(1)
    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - prev_close).abs()
    tr3 = (df["Low"] - prev_close).abs()
    df["true_range"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR14"] = df["true_range"].rolling(14).mean()

    # RSI (14 and 2 periods)
    price_diff = df["Close"].diff()
    gains = price_diff.clip(lower=0)
    losses = (-price_diff).clip(lower=0)

    # RSI14
    avg_gain14 = gains.rolling(14).mean()
    avg_loss14 = losses.rolling(14).mean().replace(0, np.nan)
    rs14 = avg_gain14 / avg_loss14
    df["RSI14"] = 100 - (100 / (1 + rs14))

    # RSI2
    avg_gain2 = gains.rolling(2).mean()
    avg_loss2 = losses.rolling(2).mean().replace(0, np.nan)
    rs2 = avg_gain2 / avg_loss2
    df["RSI2"] = 100 - (100 / (1 + rs2))

    # 52-week High and Low
    df["HIGH52W"] = df["High"].rolling(252, min_periods=50).max()
    df["LOW52W"] = df["Low"].rolling(252, min_periods=50).min()

    # 20-day High and Low excluding today
    df["HIGH20"] = df["High"].rolling(20).max().shift(1)
    df["LOW20"] = df["Low"].rolling(20).min().shift(1)

    # 20-day Exponential Moving Average
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()

    # On-Balance Volume (OBV) & 20-day OBV high
    price_change = df["Close"].diff()
    obv_dir = pd.Series(np.where(price_change > 0, 1.0, np.where(price_change < 0, -1.0, 0.0)), index=df.index)
    obv_dir.iloc[0] = 0.0
    df["OBV"] = (df["Volume"] * obv_dir).cumsum()
    df["OBV_HIGH20"] = df["OBV"].rolling(20).max().shift(1)
    if "OBV_CONFIRM" not in df.columns:
        df["OBV_CONFIRM"] = df["OBV"] > df["OBV_HIGH20"]

    # Trend Filter (Minervini / O'Neil style)
    df["TREND_OK"] = (
        (df["Close"] > df["SMA150"])
        & (df["Close"] > df["SMA200"])
        & (df["SMA150"] > df["SMA200"])
        & (df["SMA200"] > df["SMA200"].shift(50))
        & (df["SMA50"] > df["SMA150"])
        & (df["SMA50"] > df["SMA200"])
        & (df["Close"] > df["SMA50"])
        & (df["Close"] > 1.30 * df["LOW52W"])
        & (df["Close"] > 0.75 * df["HIGH52W"])
    )

    # Setup conditions: volume contraction & price tightening
    df["VOL_DRYUP"] = df["VOL5"] < (0.80 * df["VOL50"])
    df["PRICE_TIGHT"] = df["RANGE5"] < (0.80 * df["RANGE50"])
    df["SETUP_OK"] = df["VOL_DRYUP"] & df["PRICE_TIGHT"]

    # Squeeze condition: Bollinger Bands inside Keltner Channels
    sma20 = df["Close"].rolling(20).mean()
    std20 = df["Close"].rolling(20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20

    atr20 = df["true_range"].rolling(20).mean()
    kc_upper = sma20 + 1.5 * atr20
    kc_lower = sma20 - 1.5 * atr20
    df["SQUEEZE_ON"] = (bb_upper < kc_upper) & (bb_lower > kc_lower)

    # Setup window: active if setup or squeeze occurred within SETUP_WINDOW_DAYS, shifted by 1 day
    coiling = df["SETUP_OK"] | (df["SQUEEZE_ON"] if ENABLE_SQUEEZE else False)
    df["SETUP_WINDOW"] = coiling.astype(float).rolling(SETUP_WINDOW_DAYS).max().shift(1) > 0

    # Breakout triggers
    df["BREAKOUT"] = (df["Close"] > df["HIGH20"]) & (df["Close"].shift(1) <= df["HIGH20"])
    
    # Small-cap volume spike: >= 2.0x 50-day average volume AND 3-day rising volume across breakout window
    vol_today = df["Volume"]
    vol_yesterday = df["Volume"].shift(1)
    vol_2days_ago = df["Volume"].shift(2)
    vol50 = df["VOL50"]
    vol_spike_today = vol_today >= (VOLUME_SPIKE_MIN * vol50)
    vol_rising_3day = (vol_today > vol_yesterday) & (vol_yesterday > vol_2days_ago) & (vol_2days_ago >= 0.3 * vol50)
    df["VOL_SPIKE"] = vol_spike_today & vol_rising_3day

    # Strong close (>60% of candle's range)
    safe_hl = (df["High"] - df["Low"]).replace(0, np.nan)
    df["STRONG_CLOSE"] = ((df["Close"] - df["Low"]) / safe_hl) > 0.60

    # Rising RS slope gate (slope >= +2 percentile-points / week)
    if "RS_SLOPE_OK" not in df.columns:
        slope_val = calculate_weekly_rs_slope(df)
        df["RS_SLOPE_OK"] = slope_val >= 2.0

    # Momentum rank cutoff gate (volatility-adjusted 6-month return > 0)
    if "MOMENTUM_OK" not in df.columns:
        vol_adj = calculate_vol_adj_return(df)
        df["MOMENTUM_OK"] = (vol_adj is not None) and (vol_adj > 0)

    # Edge: SPRING trigger (new entry class)
    # Over 20-day base, price breaks below 20-day low intraday but closes back above on >=1.5x avg volume
    df["SPRING"] = (
        df["TREND_OK"]
        & (df["Low"] < df["LOW20"])
        & (df["Close"] > df["LOW20"])
        & (df["Volume"] >= 1.5 * df["VOL50"])
    )

    # Edge: REFINED PULLBACK (set ENABLE_PULLBACK=True)
    # Confirmed Stage-2 name, pullback to 20-EMA on declining volume, reclaimed by green candle
    pullback_touch = df["Low"] <= (df["EMA20"] * 1.01)
    reclaimed_green = (df["Close"] > df["EMA20"]) & (df["Close"] > df["Open"])
    vol_declining = df["Volume"] < df["VOL50"]
    df["PULLBACK"] = df["TREND_OK"] & pullback_touch & reclaimed_green & vol_declining

    # Master signals
    df["SIGNAL"] = (
        df["TREND_OK"]
        & df["SETUP_WINDOW"]
        & df["BREAKOUT"]
        & df["VOL_SPIKE"]
        & df["STRONG_CLOSE"]
        & df["OBV_CONFIRM"]
        & df["RS_SLOPE_OK"]
        & df["MOMENTUM_OK"]
    )
    df["SIGNAL_SPRING"] = (
        df["TREND_OK"]
        & df["SPRING"]
        & df["RS_SLOPE_OK"]
        & df["MOMENTUM_OK"]
    )
    df["SIGNAL_PULLBACK"] = (
        df["TREND_OK"]
        & df["PULLBACK"]
        & df["RS_SLOPE_OK"]
        & df["MOMENTUM_OK"]
    )

    # Clean boolean columns (replace NaN with False)
    boolean_columns = [
        "TREND_OK",
        "VOL_DRYUP",
        "PRICE_TIGHT",
        "SETUP_OK",
        "SQUEEZE_ON",
        "SETUP_WINDOW",
        "BREAKOUT",
        "VOL_SPIKE",
        "STRONG_CLOSE",
        "OBV_CONFIRM",
        "RS_SLOPE_OK",
        "MOMENTUM_OK",
        "PULLBACK",
        "SPRING",
        "SIGNAL",
        "SIGNAL_PULLBACK",
        "SIGNAL_SPRING",
    ]
    for col in boolean_columns:
        df[col] = df[col].fillna(False).astype(bool)

    return df


# =====================================================================
# 6) SMALL-CAP REGIME FILTER (EQUAL-WEIGHT BASKET)
# =====================================================================
_INDEX_CACHE: Optional[pd.DataFrame] = None
_BASKET_CACHE: Optional[pd.DataFrame] = None


def get_cached_index_df() -> Optional[pd.DataFrame]:
    """Retrieve and cache the benchmark index history."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        idx_df = get_history(INDEX_SYMBOL)
        if idx_df is not None and not idx_df.empty:
            _INDEX_CACHE = add_indicators(idx_df)
    return _INDEX_CACHE


def get_basket_df(symbols: Optional[List[str]] = None, force_rebuild: bool = False) -> Optional[pd.DataFrame]:
    """
    Build and cache an equal-weight basket index series from universe constituents:
    - Collect historical Close for each symbol with >=200 bars.
    - Require >=80% of symbols in the universe to have valid data, else regime is UNAVAILABLE.
    - Normalize Close to 1.0 at oldest common date.
    - Average across symbols per day (equal weight).
    """
    global _BASKET_CACHE
    if _BASKET_CACHE is not None and not force_rebuild:
        return _BASKET_CACHE

    if symbols is None:
        symbols = get_symbols()
    if not symbols:
        return None

    total_symbols = len(symbols)
    valid_dfs: Dict[str, pd.Series] = {}

    for sym in symbols:
        df_sym = get_history(sym)
        if df_sym is not None and not df_sym.empty and len(df_sym) >= 200:
            df_s = df_sym.copy()
            df_s["Date"] = pd.to_datetime(df_s["Date"])
            df_s = df_s.sort_values("Date").drop_duplicates(subset=["Date"])
            valid_dfs[sym] = df_s.set_index("Date")["Close"]

    min_required_symbols = math.ceil(BASKET_MIN_SYMBOLS_PCT * total_symbols)
    if len(valid_dfs) < min_required_symbols or len(valid_dfs) == 0:
        return None

    combined = pd.DataFrame(valid_dfs)
    valid_rows = combined.dropna(thresh=min_required_symbols)
    if len(valid_rows) < 200:
        return None

    first_row = valid_rows.bfill().iloc[0]
    first_row = first_row.replace(0, np.nan)
    normalized = valid_rows.div(first_row)

    basket_close = normalized.mean(axis=1)

    basket_df = pd.DataFrame({
        "Date": valid_rows.index,
        "Close": basket_close.values,
    })
    basket_df["SMA50"] = basket_df["Close"].rolling(50).mean()
    basket_df["SMA200"] = basket_df["Close"].rolling(200).mean()
    basket_df["HIGH20"] = basket_df["Close"].rolling(20).max()

    _BASKET_CACHE = basket_df
    return basket_df


def regime_ok() -> bool:
    """
    Equal-weight basket regime filter for small caps (fail-closed).
    Returns True if:
      basket_close > basket_SMA50
      AND basket_close > basket_SMA200
      AND basket_SMA50 > basket_SMA200
      AND (basket_close / basket_20d_high - 1) > -0.07 (sharp-drawdown guard).
    If basket cannot be built (e.g. <80% valid symbols), returns False.
    """
    b_df = get_basket_df()
    if b_df is None or len(b_df) < 200:
        return False

    last_row = b_df.iloc[-1]
    c = float(last_row["Close"])
    sma50 = float(last_row["SMA50"])
    sma200 = float(last_row["SMA200"])
    high20 = float(last_row["HIGH20"])

    if pd.isna(c) or pd.isna(sma50) or pd.isna(sma200) or pd.isna(high20) or high20 <= 0:
        return False

    dd = (c / high20) - 1.0
    is_ok = (c > sma50) and (c > sma200) and (sma50 > sma200) and (dd > BASKET_DRAWDOWN_GUARD_PCT)
    if not is_ok:
        return False

    # Optional secondary crash-check on large-cap benchmark (^NSEI)
    if USE_LARGE_CAP_CRASH_CHECK:
        idx_df = get_cached_index_df()
        if idx_df is not None and len(idx_df) >= 200:
            idx_last = idx_df.iloc[-1]
            if not ((idx_last["Close"] > idx_last["SMA200"]) or (idx_last["Close"] > idx_last["SMA50"])):
                return False

    return True


_real_regime_ok = regime_ok


def market_ok() -> bool:
    """Alias for regime_ok to preserve backward compatibility."""
    return regime_ok()


def index_return_50() -> Optional[float]:
    """
    50-day return of the equal-weight basket (or benchmark index if basket unavailable).
    """
    b_df = get_basket_df()
    if b_df is not None and len(b_df) >= 51:
        last_close = float(b_df["Close"].iloc[-1])
        close_50 = float(b_df["Close"].iloc[-51])
        if close_50 > 0:
            return float((last_close / close_50) - 1.0)

    idx_df = get_cached_index_df()
    if idx_df is None or len(idx_df) < 51:
        return None

    last_close = float(idx_df["Close"].iloc[-1])
    close_50 = float(idx_df["Close"].iloc[-51])
    if close_50 <= 0:
        return None

    return float((last_close / close_50) - 1.0)


# =====================================================================
# CIRCUIT, EARNINGS & HEAT GUARDS (SMALL-CAP SURVIVAL LAYER)
# =====================================================================
def load_circuits() -> Dict[str, float]:
    """Load circuit band map from circuits.json if present."""
    if not os.path.exists(CIRCUITS_FILE):
        return {}
    try:
        with open(CIRCUITS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def check_circuit_proximity(symbol: str, df: pd.DataFrame) -> Tuple[bool, Optional[str]]:
    """
    Skip entry if last close is within 2% of the upper or lower band computed vs previous close.
    Default band is 0.10 (10%) if circuits.json missing or symbol unlisted.
    """
    if len(df) < 2:
        return False, None

    circuits = load_circuits()
    clean_sym = symbol.replace(".NS", "").upper()
    band_pct = circuits.get(symbol, circuits.get(clean_sym, DEFAULT_CIRCUIT_BAND))

    prev_close = float(df["Close"].iloc[-2])
    last_close = float(df["Close"].iloc[-1])
    if prev_close <= 0 or last_close <= 0:
        return False, None

    upper_band = prev_close * (1.0 + band_pct)
    lower_band = prev_close * (1.0 - band_pct)

    if last_close >= upper_band * (1.0 - CIRCUIT_PROXIMITY_PCT):
        return True, f"Within 2% of upper circuit band (₹{upper_band:.2f})"
    if last_close <= lower_band * (1.0 + CIRCUIT_PROXIMITY_PCT):
        return True, f"Within 2% of lower circuit band (₹{lower_band:.2f})"

    return False, None


def load_earnings_dates() -> Dict[str, str]:
    """Load earnings date map from earnings_dates.json."""
    if not os.path.exists(EARNINGS_FILE):
        return {}
    try:
        with open(EARNINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_next_earnings(symbol: str) -> Optional[str]:
    """Get next earnings date for a symbol if registered."""
    dates = load_earnings_dates()
    clean_sym = symbol.replace(".NS", "").upper()
    return dates.get(symbol) or dates.get(clean_sym)


def check_earnings_blackout(symbol: str, current_date: datetime.date) -> Tuple[bool, str]:
    """
    Fail-closed earnings check for small caps:
    If symbol has NO entry -> treat next earnings as UNKNOWN -> BLOCK entry.
    If next earnings is within EARNINGS_BLACKOUT_DAYS (5 days) -> BLOCK entry.
    """
    next_earn_str = get_next_earnings(symbol)
    if not next_earn_str:
        return True, "UNKNOWN->blocked"

    try:
        earn_date = datetime.date.fromisoformat(next_earn_str)
        delta_days = (earn_date - current_date).days
        if 0 <= delta_days <= EARNINGS_BLACKOUT_DAYS:
            return True, next_earn_str
        return False, next_earn_str
    except Exception:
        return True, "UNKNOWN->blocked"


# =====================================================================
# INSTITUTIONAL FOOTPRINT & EVENT RADAR (INDIAN-MARKET MOATS)
# =====================================================================
def load_deals() -> Dict[str, Dict[str, Any]]:
    """Safely load institutional deals from deals.json."""
    if not os.path.exists(DEALS_FILE):
        return {}
    try:
        with open(DEALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def is_deals_stale(deals: Optional[Dict[str, Any]] = None, current_date: Optional[datetime.date] = None) -> bool:
    """
    Returns True if deals data is missing or older than 3 calendar/trading days.
    """
    if deals is None:
        deals = load_deals()
    if not deals or not isinstance(deals, dict):
        return True

    if current_date is None:
        current_date = datetime.date.today()

    valid_dates = []
    for d_str in deals.keys():
        try:
            valid_dates.append(datetime.date.fromisoformat(d_str))
        except Exception:
            pass

    if not valid_dates:
        return True

    latest_date = max(valid_dates)
    delta_days = (current_date - latest_date).days
    return delta_days > 3


def classify_inst_footprint(
    symbol: str,
    df: Optional[pd.DataFrame] = None,
    deals: Optional[Dict[str, Any]] = None
) -> str:
    """
    Classify institutional footprint for symbol into {accumulation, churn, unknown}.
    - accumulation = rising delivery% vs 5d-avg with price flat/up OR an inst print in last 3 sessions;
    - churn = vol >= 1.5x avg AND delivery% < 25% AND no print;
    - else unknown.
    Fail-open: missing data => 'unknown'.
    """
    if deals is None:
        deals = load_deals()
    if not deals or not isinstance(deals, dict):
        return "unknown"

    clean_sym = symbol.replace(".NS", "").upper()
    sym_variants = [symbol, clean_sym, f"{clean_sym}.NS"]

    sorted_dates = sorted(deals.keys())
    if not sorted_dates:
        return "unknown"

    # 1. Check for institutional print in the last 3 available sessions
    has_inst_print = False
    last_3_dates = sorted_dates[-3:]
    for d in last_3_dates:
        day_deals = deals.get(d, {})
        for s in sym_variants:
            if s in day_deals:
                entry = day_deals[s]
                if entry.get("block_print") or entry.get("bulk_print") or bool(entry.get("inst_name")):
                    has_inst_print = True
                    break
        if has_inst_print:
            break

    # 2. Check delivery% on latest session vs 5-day average
    cur_deliv: Optional[float] = None
    latest_date = sorted_dates[-1]
    latest_day_deals = deals.get(latest_date, {})
    for s in sym_variants:
        if s in latest_day_deals and latest_day_deals[s].get("delivery_pct") is not None:
            try:
                cur_deliv = float(latest_day_deals[s]["delivery_pct"])
                break
            except Exception:
                pass

    rising_deliv = False
    if cur_deliv is not None and len(sorted_dates) >= 2:
        prev_dates = sorted_dates[:-1][-5:]
        deliv_hist = []
        for d in prev_dates:
            d_deals = deals.get(d, {})
            for s in sym_variants:
                if s in d_deals and d_deals[s].get("delivery_pct") is not None:
                    try:
                        deliv_hist.append(float(d_deals[s]["delivery_pct"]))
                        break
                    except Exception:
                        pass
        if deliv_hist:
            avg_5d = sum(deliv_hist) / len(deliv_hist)
            rising_deliv = (cur_deliv > avg_5d)

    # 3. Price flat/up and volume spike from df
    price_flat_or_up = False
    vol_spike = False
    if df is not None and len(df) >= 2:
        try:
            c_last = float(df["Close"].iloc[-1])
            c_prev = float(df["Close"].iloc[-2])
            price_flat_or_up = (c_last >= c_prev - 1e-4)

            last_vol = float(df["Volume"].iloc[-1])
            if "VOL50" in df and not pd.isna(df["VOL50"].iloc[-1]):
                v50 = float(df["VOL50"].iloc[-1])
            else:
                v50 = float(df["Volume"].rolling(50).mean().iloc[-1])
            vol_spike = (last_vol >= 1.5 * v50) or bool(df.iloc[-1].get("VOL_SPIKE", False))
        except Exception:
            pass

    # 4. Final classification
    if (rising_deliv and price_flat_or_up) or has_inst_print:
        return "accumulation"
    elif vol_spike and (cur_deliv is not None and cur_deliv < 25.0) and not has_inst_print:
        return "churn"
    return "unknown"


def load_events() -> Dict[str, List[Dict[str, Any]]]:
    """Safely load scheduled corporate events from events.json."""
    if not os.path.exists(EVENTS_FILE):
        return {}
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_all_symbol_events(symbol: str, current_date: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
    """
    Get all upcoming events for a symbol by merging events.json and earnings_dates.json.
    Each event dict: {type, date, days_to_event, note}.
    """
    if current_date is None:
        current_date = datetime.date.today()

    events_map = load_events()
    clean_sym = symbol.replace(".NS", "").upper()
    sym_events = events_map.get(symbol, []) or events_map.get(clean_sym, []) or []

    merged: List[Dict[str, Any]] = []

    # 1. From events.json
    for ev in sym_events:
        d_str = ev.get("date")
        if not d_str:
            continue
        try:
            ev_date = datetime.date.fromisoformat(d_str)
            days = (ev_date - current_date).days
            if days >= 0:
                merged.append({
                    "type": str(ev.get("type", "OTHER")).upper(),
                    "date": d_str,
                    "days_to_event": days,
                    "note": str(ev.get("note", "")),
                })
        except Exception:
            continue

    # 2. Auto-merge earnings from earnings_dates.json / get_next_earnings
    earn_str = get_next_earnings(symbol)
    if earn_str:
        try:
            earn_date = datetime.date.fromisoformat(earn_str)
            days = (earn_date - current_date).days
            if days >= 0 and not any(e["type"] == "EARNINGS" and e["date"] == earn_str for e in merged):
                merged.append({
                    "type": "EARNINGS",
                    "date": earn_str,
                    "days_to_event": days,
                    "note": "Quarterly Financial Results",
                })
        except Exception:
            pass

    merged.sort(key=lambda x: (x["days_to_event"], x["date"]))
    return merged


def get_next_event(symbol: str, current_date: Optional[datetime.date] = None) -> Optional[Dict[str, Any]]:
    """
    Returns the nearest upcoming event for a symbol, or None if none scheduled.
    """
    all_events = get_all_symbol_events(symbol, current_date)
    return all_events[0] if all_events else None


def get_landmines(symbols: List[str], current_date: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
    """
    Events within 7 days for any watchlist, on-deck, or open position symbol.
    Sorted by days_to_event ascending.
    """
    if current_date is None:
        current_date = datetime.date.today()

    landmines: List[Dict[str, Any]] = []
    seen = set()

    for sym in symbols:
        events = get_all_symbol_events(sym, current_date)
        for ev in events:
            if 0 <= ev["days_to_event"] <= 7:
                key = (sym, ev["type"], ev["date"])
                if key not in seen:
                    seen.add(key)
                    landmines.append({
                        "symbol": sym,
                        "type": ev["type"],
                        "date": ev["date"],
                        "days_to_event": ev["days_to_event"],
                        "note": ev.get("note", ""),
                    })

    landmines.sort(key=lambda x: (x["days_to_event"], x["symbol"]))
    return landmines


def check_event_or_earnings_blackout(symbol: str, current_date: datetime.date) -> Tuple[bool, str]:
    """
    ENTRY gate: Generalizes the S2 earnings-blackout so ANY known gap-event
    within EARNINGS_BLACKOUT_DAYS blocks a NEW entry.
    Fail-closed when known & near; unknown earnings => blocked;
    unknown general event (no entry in events.json) => allowed.
    """
    # 1. Earnings blackout check first (maintains S2 fail-closed on unknown earnings)
    earn_blocked, earn_info = check_earnings_blackout(symbol, current_date)
    if earn_blocked:
        return True, earn_info

    # 2. General corporate events from events.json (AGM, LOCKIN, RECORD, DIVIDEND, etc.)
    events_map = load_events()
    clean_sym = symbol.replace(".NS", "").upper()
    sym_events = events_map.get(symbol, []) or events_map.get(clean_sym, []) or []

    for ev in sym_events:
        d_str = ev.get("date")
        if not d_str:
            continue
        try:
            ev_date = datetime.date.fromisoformat(d_str)
            delta = (ev_date - current_date).days
            if 0 <= delta <= EARNINGS_BLACKOUT_DAYS:
                return True, f"{ev.get('type', 'EVENT')} on {d_str} ({delta}d)"
        except Exception:
            continue

    return False, earn_info


def check_open_positions_events(
    open_positions: List[Dict[str, Any]],
    current_date: Optional[datetime.date] = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    OPEN-position WARN only (never auto-exit):
    days_to_event <= 3 => warn_event: True + warning message line.
    NEVER touches stop/target/time-stop.
    """
    if current_date is None:
        current_date = datetime.date.today()

    warn_lines: List[str] = []
    for pos in open_positions:
        sym = pos.get("symbol", "")
        next_ev = get_next_event(sym, current_date)
        pos["next_event"] = next_ev
        if next_ev and 0 <= next_ev["days_to_event"] <= 3:
            pos["warn_event"] = True
            warn_lines.append(
                f"🔔 {sym} event ({next_ev['type']}) in {next_ev['days_to_event']} days - review hold"
            )
        else:
            pos["warn_event"] = False

    return open_positions, warn_lines


def check_buy_limits(sym: str, entry_price: float, qty: int, stop: Optional[float]) -> Optional[str]:
    """
    Enforces risk and drawdown caps for /buy:
    - MAX_CONCURRENT_SMALLCAP (4)
    - MAX_TOTAL_HEAT_PCT (0.05 / 5%)
    - DAILY_STOP_PCT (0.02 / 2%)
    - MONTHLY_STOP_PCT (0.06 / 6%) - Elder circuit-breaker
    Returns error string if rejected, None if approved.
    """
    open_positions = load_open_positions()

    # 1. Concurrent positions cap
    if len(open_positions) >= MAX_CONCURRENT_SMALLCAP:
        return (
            f"⚠️ BUY REJECTED: Maximum concurrent small-cap positions reached ({MAX_CONCURRENT_SMALLCAP}). "
            f"Close an existing position before opening a new one."
        )

    # Calculate proposed trade risk
    eff_stop = stop if (stop is not None and stop < entry_price) else (entry_price * (1.0 - MAX_STOP_LOSS_PCT))
    new_risk = max(0.0, (entry_price - eff_stop) * qty)

    # 2. Total portfolio heat cap (5% of capital)
    curr_heat = 0.0
    for pos in open_positions:
        p_entry = float(pos.get("entry_price", 0))
        p_stop = float(pos.get("stop", p_entry * (1.0 - MAX_STOP_LOSS_PCT)))
        p_qty = int(pos.get("qty", 0))
        curr_heat += max(0.0, (p_entry - p_stop) * p_qty)

    total_heat = curr_heat + new_risk
    total_heat_pct = total_heat / CAPITAL
    if total_heat_pct > MAX_TOTAL_HEAT_PCT:
        return (
            f"⚠️ BUY REJECTED: Total open risk ({total_heat_pct*100:.1f}%) exceeds maximum heat limit "
            f"of {MAX_TOTAL_HEAT_PCT*100:.1f}% (₹{CAPITAL * MAX_TOTAL_HEAT_PCT:,.2f})."
        )

    # 3. Daily loss limit (2% of capital) from trades.json
    trades = load_trades()
    today_str = datetime.date.today().isoformat()
    daily_realized_loss = 0.0
    for t in trades:
        exit_date = str(t.get("exit_date", ""))
        if exit_date == today_str:
            pnl = float(t.get("pnl", 0.0))
            if pnl < 0:
                daily_realized_loss += abs(pnl)
    if daily_realized_loss >= (CAPITAL * DAILY_STOP_PCT):
        return (
            f"⚠️ BUY REJECTED: Daily stop loss limit reached (₹{daily_realized_loss:,.2f} >= "
            f"₹{CAPITAL * DAILY_STOP_PCT:,.2f}, {DAILY_STOP_PCT*100:.1f}% limit). Trading halted for today."
        )

    # 4. Monthly drawdown limit (6% of capital realized + unrealized)
    month_prefix = today_str[:7]
    monthly_realized_loss = 0.0
    for t in trades:
        exit_date = str(t.get("exit_date", ""))
        if exit_date.startswith(month_prefix):
            pnl = float(t.get("pnl", 0.0))
            monthly_realized_loss -= pnl
    monthly_realized_loss = max(0.0, monthly_realized_loss)

    monthly_unrealized_loss = 0.0
    for pos in open_positions:
        p_entry = float(pos.get("entry_price", 0))
        p_curr = float(pos.get("current_price", pos.get("entry_price", 0)))
        p_qty = int(pos.get("qty", 0))
        if p_curr < p_entry:
            monthly_unrealized_loss += (p_entry - p_curr) * p_qty

    total_month_loss = monthly_realized_loss + monthly_unrealized_loss
    if total_month_loss >= (CAPITAL * MONTHLY_STOP_PCT):
        return (
            f"⚠️ BUY REJECTED: Monthly drawdown limit reached (₹{total_month_loss:,.2f} >= "
            f"₹{CAPITAL * MONTHLY_STOP_PCT:,.2f}, {MONTHLY_STOP_PCT*100:.1f}% limit). Elder circuit-breaker active."
        )

    return None


def get_sector_df(sector_symbol: str) -> Optional[pd.DataFrame]:
    """
    Retrieve and cache historical dataframe for a given sector index.
    Ensures each sector is downloaded only once per run.
    """
    global _SECTOR_CACHE
    if sector_symbol == INDEX_SYMBOL:
        return get_cached_index_df()

    if sector_symbol not in _SECTOR_CACHE:
        df = get_history(sector_symbol)
        if df is not None and not df.empty:
            _SECTOR_CACHE[sector_symbol] = add_indicators(df)
        else:
            _SECTOR_CACHE[sector_symbol] = None
    return _SECTOR_CACHE.get(sector_symbol)


def sector_ok(symbol: str) -> bool:
    """
    Sector strength filter:
    Looks up stock's sector symbol from SECTOR_MAP (defaults to ^NSEI).
    Returns True if sector's last Close > SMA50 AND > SMA200 AND SMA50 > SMA200.
    Returns True if sector data is unavailable or fails (fail-open).
    """
    try:
        clean_sym = symbol.strip().upper()
        if not clean_sym.endswith(".NS"):
            clean_sym = f"{clean_sym}.NS"

        sector_sym = SECTOR_MAP.get(clean_sym, SECTOR_MAP.get(symbol, INDEX_SYMBOL))
        sec_df = get_sector_df(sector_sym)
        if sec_df is None or len(sec_df) < 200:
            return True  # Fail-open so a download glitch never blocks trades

        last_row = sec_df.iloc[-1]
        is_ok = (
            (last_row["Close"] > last_row["SMA50"])
            and (last_row["Close"] > last_row["SMA200"])
            and (last_row["SMA50"] > last_row["SMA200"])
        )
        return bool(is_ok)
    except Exception:
        return True  # Strictly fail-open on any unexpected error


# =====================================================================
# 6B) DECISION-MAKING & DIAGNOSTIC INTELLIGENCE
# =====================================================================
def calculate_mtf_confluence(df: pd.DataFrame, daily_trend_ok: Optional[bool] = None) -> bool:
    """
    Weekly Stage-2: resample same history to weekly.
    w_Close > w_SMA30 AND w_SMA30 rising (w_SMA30[-1] > w_SMA30[-2]).
    Confluence = daily TREND_OK AND weekly Stage-2 (bool).
    """
    if df is None or len(df) < 20:
        return False

    if daily_trend_ok is None:
        if "TREND_OK" in df.columns:
            daily_trend_ok = bool(df["TREND_OK"].iloc[-1])
        else:
            daily_trend_ok = False

    if not daily_trend_ok:
        return False

    try:
        sub = df[["Date", "Close"]].copy() if "Date" in df.columns else df[["Close"]].copy()
        if "Date" in sub.columns:
            sub["Date"] = pd.to_datetime(sub["Date"])
            sub.set_index("Date", inplace=True)
        elif not isinstance(sub.index, pd.DatetimeIndex):
            sub.index = pd.date_range(end=datetime.date.today(), periods=len(sub), freq="D")

        w_series = sub["Close"].resample("W").last().dropna()
        if len(w_series) < 5:
            return False

        # 30-week SMA with min_periods fallback for small synthetic test fixtures
        w_sma30 = w_series.rolling(30, min_periods=min(5, len(w_series))).mean()
        valid_sma = w_sma30.dropna()
        if len(valid_sma) < 2:
            return False

        w_close_last = float(w_series.iloc[-1])
        w_sma_last = float(valid_sma.iloc[-1])
        w_sma_prev = float(valid_sma.iloc[-2])

        w_stage2 = (w_close_last > w_sma_last) and (w_sma_last > w_sma_prev)
        return bool(daily_trend_ok and w_stage2)
    except Exception:
        return False


def build_thesis_card(item: Dict[str, Any]) -> str:
    """
    Assembles a 4-line plain-English string ONLY from existing fields (None -> 'n/a'):
    L1 "GRADE <g> | RS <rs> | Base <maturity>/4 (<days>d)"
    L2 "Trend <✓/✗> / Setup <coiling?> / Sector <bullish?> / MTF <✓/—>"
    L3 "Inst: <footprint> | Next event: <type in Nd or none>"
    L4 "Plan: <exit_plan> | Risk 1% (gap-capped @20%)"
    Pure formatting, no new thresholds.
    """
    # L1: GRADE <g> | RS <rs> | Base <maturity>/4 (<days>d)
    g = item.get("grade") or item.get("Grade") or "n/a"
    rs = item.get("rs_rating")
    if rs is not None and not (isinstance(rs, float) and math.isnan(rs)):
        rs_str = str(int(round(rs)))
    else:
        rs_str = "n/a"

    mat = item.get("base_maturity")
    mat_str = str(mat) if mat is not None else "n/a"
    days = item.get("days_in_base")
    days_str = str(days) if days is not None else "n/a"
    l1 = f"GRADE {g} | RS {rs_str} | Base {mat_str}/4 ({days_str}d)"

    # L2: Trend <✓/✗> / Setup <coiling?> / Sector <bullish?> / MTF <✓/—>
    trend = item.get("Trend")
    if trend == "YES" or trend is True:
        trend_sym = "✓"
    elif trend == "no" or trend is False:
        trend_sym = "✗"
    else:
        trend_sym = "✓" if item.get("TREND_OK", True) else "✗"

    coiling = item.get("Coiling")
    if coiling == "YES" or coiling is True or item.get("SETUP_OK"):
        setup_str = "Coiling"
    else:
        setup_str = "Consolidating"

    sec_bullish = item.get("SectorBullish")
    if sec_bullish == "YES" or sec_bullish is True:
        sec_str = "Bullish"
    elif sec_bullish == "no" or sec_bullish is False:
        sec_str = "Neutral"
    else:
        sec_str = "n/a"

    mtf = item.get("mtf_confluence")
    mtf_sym = "✓" if mtf else "—"
    l2 = f"Trend {trend_sym} / Setup {setup_str} / Sector {sec_str} / MTF {mtf_sym}"

    # L3: Inst: <footprint> | Next event: <type in Nd or none>
    inst = item.get("inst_footprint") or "unknown"
    next_ev = item.get("next_event")
    if isinstance(next_ev, dict) and next_ev.get("type"):
        d = next_ev.get("days_to_event")
        d_str = f"{d}d" if d is not None else "n/a"
        ev_str = f"{next_ev['type']} in {d_str}"
    else:
        ev_str = "none"
    l3 = f"Inst: {inst} | Next event: {ev_str}"

    # L4: Plan: <exit_plan> | Risk 1% (gap-capped @20%)
    if item.get("Target") and item.get("Stop"):
        exit_plan = f"Target ₹{item['Target']} (2R) / Stop ₹{item['Stop']}"
    elif item.get("breakout_level"):
        exit_plan = f"GTT Breakout ₹{item['breakout_level']} / Target 2R"
    else:
        exit_plan = "2R Target / Trail 20-EMA"
    l4 = f"Plan: {exit_plan} | Risk 1% (gap-capped @20%)"

    return f"{l1}\n{l2}\n{l3}\n{l4}"


def compute_open_positions_correlation(
    open_positions: Optional[List[Dict[str, Any]]] = None,
    history_map: Optional[Dict[str, pd.DataFrame]] = None
) -> Dict[str, Any]:
    """
    Correlation among OPEN positions only:
    pairwise 60d daily-return Pearson + each position beta to the universe basket;
    output: correlation={pairs:[{a,b,corr}],betas:{},concentration_warning:(any pair>0.7) OR (>2 same-sector)}.
    Graceful: <2 open => pairs [], warning False (no div-by-zero).
    """
    if open_positions is None:
        open_positions = load_open_positions()

    valid_positions = [p for p in (open_positions or []) if p and p.get("symbol")]
    symbols = list(dict.fromkeys(p["symbol"] for p in valid_positions))

    if len(symbols) < 2:
        return {
            "pairs": [],
            "betas": {},
            "concentration_warning": False,
        }

    daily_rets: Dict[str, pd.Series] = {}
    for sym in symbols:
        df = history_map.get(sym) if history_map else get_history(sym)
        if df is not None and len(df) >= 2:
            rets = df["Close"].pct_change().dropna()
            if len(rets) > 0:
                daily_rets[sym] = rets.iloc[-60:]

    pairs: List[Dict[str, Any]] = []
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            s_a = symbols[i]
            s_b = symbols[j]
            corr_val = 0.0
            if s_a in daily_rets and s_b in daily_rets:
                r_a = daily_rets[s_a]
                r_b = daily_rets[s_b]
                common = pd.concat([r_a, r_b], axis=1, join="inner").dropna()
                if len(common) >= 5:
                    c = float(common.iloc[:, 0].corr(common.iloc[:, 1]))
                    if not math.isnan(c):
                        corr_val = round(c, 2)
            pairs.append({"a": s_a, "b": s_b, "corr": corr_val})

    # Position beta to the universe basket
    universe_syms = get_symbols() or []
    basket_series_list: List[pd.Series] = []
    for u_sym in universe_syms[:30]:
        if history_map is not None and u_sym in history_map:
            df_u = history_map[u_sym]
        elif u_sym in daily_rets:
            df_u = daily_rets[u_sym]
        else:
            df_u = get_history(u_sym)

        if isinstance(df_u, pd.DataFrame) and len(df_u) >= 2:
            r = df_u["Close"].pct_change().dropna().iloc[-60:]
            if len(r) >= 5:
                basket_series_list.append(r)
        elif isinstance(df_u, pd.Series) and len(df_u) >= 5:
            basket_series_list.append(df_u)

    betas: Dict[str, float] = {}
    basket_return = None
    if basket_series_list:
        try:
            basket_df = pd.concat(basket_series_list, axis=1).mean(axis=1).dropna()
            if len(basket_df) >= 5:
                basket_return = basket_df
        except Exception:
            basket_return = None

    for sym in symbols:
        if sym in daily_rets and basket_return is not None:
            r_sym = daily_rets[sym]
            common = pd.concat([r_sym, basket_return], axis=1, join="inner").dropna()
            if len(common) >= 5:
                var_m = float(common.iloc[:, 1].var())
                if var_m > 1e-8:
                    cov_sm = float(common.iloc[:, 0].cov(common.iloc[:, 1]))
                    b_val = round(float(cov_sm / var_m), 2)
                    betas[sym] = b_val if not math.isnan(b_val) else 1.0
                else:
                    betas[sym] = 1.0
            else:
                betas[sym] = 1.0
        else:
            betas[sym] = 1.0

    # Concentration warning: (any pair > 0.7) OR (>2 same-sector)
    any_high_corr = any(p["corr"] > 0.7 for p in pairs)
    sector_counts: Dict[str, int] = {}
    for p in valid_positions:
        sec = p.get("sector") or SECTOR_MAP.get(p.get("symbol"), INDEX_SYMBOL)
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
    more_than_two_same_sector = any(cnt > 2 for cnt in sector_counts.values())

    concentration_warning = bool(any_high_corr or more_than_two_same_sector)

    return {
        "pairs": pairs,
        "betas": betas,
        "concentration_warning": concentration_warning,
    }


def compute_sector_rotation(
    symbols: Optional[List[str]] = None,
    history_map: Optional[Dict[str, pd.DataFrame]] = None,
    on_deck: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Group universe by sector;
    per sector {sector, n, pct_above_sma50, avg_ret_126d, on_deck_count};
    sort by a composite leadership score;
    output top 8 + a per-sector map so the table can color/filter by sector.
    """
    if symbols is None:
        symbols = get_symbols() or []

    if on_deck is None:
        on_deck = []

    on_deck_sector_counts: Dict[str, int] = {}
    for od in on_deck:
        od_sym = od.get("symbol") or ""
        od_sec = SECTOR_MAP.get(od_sym, INDEX_SYMBOL)
        on_deck_sector_counts[od_sec] = on_deck_sector_counts.get(od_sec, 0) + 1

    sectors_data: Dict[str, Dict[str, Any]] = {}
    for sym in symbols:
        sec = SECTOR_MAP.get(sym, INDEX_SYMBOL)
        if sec not in sectors_data:
            sectors_data[sec] = {
                "symbols": [],
                "above_sma50_count": 0,
                "rets_126d": [],
            }
        sectors_data[sec]["symbols"].append(sym)

        df = history_map.get(sym) if history_map else get_history(sym)
        if df is not None and len(df) >= 2:
            close_last = float(df["Close"].iloc[-1])
            if len(df) >= 50:
                sma50_val = float(df["Close"].rolling(50).mean().iloc[-1])
                if not math.isnan(sma50_val) and close_last > sma50_val:
                    sectors_data[sec]["above_sma50_count"] += 1
            else:
                if close_last > float(df["Close"].mean()):
                    sectors_data[sec]["above_sma50_count"] += 1

            if len(df) >= 127:
                c_prev = float(df["Close"].iloc[-127])
                if c_prev > 0 and not math.isnan(c_prev) and not math.isnan(close_last):
                    sectors_data[sec]["rets_126d"].append(((close_last / c_prev) - 1.0) * 100.0)
            elif len(df) > 1:
                c_first = float(df["Close"].iloc[0])
                if c_first > 0:
                    sectors_data[sec]["rets_126d"].append(((close_last / c_first) - 1.0) * 100.0)

    compiled: List[Dict[str, Any]] = []
    sector_map: Dict[str, Dict[str, Any]] = {}

    for sec, data in sectors_data.items():
        n = len(data["symbols"])
        pct_above_sma50 = round((data["above_sma50_count"] / max(1, n)) * 100.0, 1)
        rets = data["rets_126d"]
        avg_ret_126d = round(float(sum(rets) / len(rets)), 1) if rets else 0.0
        on_deck_cnt = on_deck_sector_counts.get(sec, 0)

        composite_score = round(
            (0.5 * pct_above_sma50) + (0.3 * avg_ret_126d) + (0.2 * (on_deck_cnt * 20.0)),
            2
        )

        item = {
            "sector": sec,
            "n": n,
            "pct_above_sma50": pct_above_sma50,
            "avg_ret_126d": avg_ret_126d,
            "on_deck_count": on_deck_cnt,
            "score": composite_score,
        }
        compiled.append(item)
        sector_map[sec] = item

    compiled.sort(key=lambda x: -x["score"])
    top_8 = compiled[:8]

    return {
        "top_sectors": top_8,
        "sector_map": sector_map,
        "sectors": sector_map,
    }


def calculate_position_risk_parameters(
    entry: float,
    atr: float,
    signal_type: str = "BREAKOUT",
    low_price: Optional[float] = None,
    capital: float = CAPITAL,
) -> Optional[Dict[str, Any]]:
    """
    Standard position sizing, ATR stop loss, 9% floor cap, and 2R profit targets.
    Single source of truth used across live scanning and rules-replay backtesting.
    """
    if pd.isna(entry) or pd.isna(atr) or atr <= 0 or entry <= 0:
        return None

    if signal_type == "SPRING":
        # Initial stop placed below the spring low (tighter than 2.5 ATR default)
        spring_low = float(low_price) if (low_price is not None and not pd.isna(low_price)) else (entry - 0.5 * atr)
        stop = min(spring_low - 0.05, entry - 0.5 * atr)
    elif signal_type == "PULLBACK":
        # Stop below the pullback low
        pullback_low = float(low_price) if (low_price is not None and not pd.isna(low_price)) else (entry - 0.5 * atr)
        stop = min(pullback_low - 0.05, entry - 0.5 * atr)
    else:
        stop = entry - (ATR_STOP_MULTIPLIER * atr)

    # Floor stop loss at MAX_STOP_LOSS_PCT (9% maximum risk from entry)
    stop = max(stop, entry * (1.0 - MAX_STOP_LOSS_PCT))
    if stop >= entry:
        return None

    # Sizing and target (gap / circuit survival sizing)
    risk_per_unit = entry - stop
    target = entry + (TARGET_R_MULTIPLE * risk_per_unit)
    gap_based_qty = math.floor((capital * MAX_GAP_LOSS_PCT) / (entry * WORST_CASE_GAP_PCT))
    risk_based_qty = math.floor((capital * RISK_PCT) / risk_per_unit)
    qty = min(risk_based_qty, gap_based_qty)
    if qty <= 0:
        return None

    risk_amount = qty * risk_per_unit

    return {
        "Entry": round(entry, 2),
        "Stop": round(stop, 2),
        "Target": round(target, 2),
        "Qty": int(qty),
        "Risk Per Unit": round(risk_per_unit, 2),
        "Risk Amount": round(risk_amount, 2),
        "gap_based_qty": gap_based_qty,
        "risk_based_qty": risk_based_qty,
        "gap_qty_applied": bool(gap_based_qty < risk_based_qty),
    }


# =====================================================================
# 7) SINGLE SYMBOL SCANNER & POSITION SIZER
# =====================================================================
def scan_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Scan an individual symbol for Breakout or Pullback swing setups.
    Calculates entry, stop loss, profit target, and position quantity.
    """
    df = get_history(symbol)
    if df is None or len(df) < 220:
        return None

    df = add_indicators(df)

    # 1) Position-aware liquidity filter
    # Compute ADV20_rupees = mean(Volume*Close) over last 20 rows.
    # Hard sanity floor: ADV20_rupees >= 50,000,000 (5 crore) else skip
    adv20_rupees = float((df["Volume"] * df["Close"]).iloc[-20:].mean())
    if adv20_rupees < ADV20_MIN_RUPEES:
        return None

    # 2) Circuit proximity check
    circuit_skip, circuit_reason = check_circuit_proximity(symbol, df)
    if circuit_skip:
        return None

    # 3) Relative strength filter: 50-day stock return must beat index/basket 50-day return
    idx_ret = index_return_50()
    if idx_ret is not None and len(df) >= 60:
        stock_close_now = df["Close"].iloc[-1]
        stock_close_50 = df["Close"].iloc[-51]
        if stock_close_50 <= 0:
            return None
        stock_ret_50 = (stock_close_now / stock_close_50) - 1.0
        if stock_ret_50 <= idx_ret:
            return None

    # 4) Sector strength filter: stock's sector index must be in an uptrend
    if not sector_ok(symbol):
        return None

    # 5) Earnings & Event blackout check (fail-closed)
    last_row = df.iloc[-1]
    curr_date = pd.to_datetime(last_row["Date"]).date() if "Date" in last_row else datetime.date.today()
    is_blocked, next_earnings = check_event_or_earnings_blackout(symbol, curr_date)
    if is_blocked:
        return None

    # 6) Setup trigger check
    if last_row.get("SIGNAL", False):
        signal_type = "BREAKOUT"
    elif last_row.get("SIGNAL_SPRING", False):
        signal_type = "SPRING"
    elif ENABLE_PULLBACK and last_row.get("SIGNAL_PULLBACK", False):
        signal_type = "PULLBACK"
    else:
        return None

    # 6b) Catalyst gate by grade: B-grade signals additionally require an identifiable catalyst OR an institutional print (else suppressed); A/A+ exempt.
    grade = "A"
    try:
        diag = diagnose(symbol)
        if diag:
            grade = diag.get("grade", "A")
    except Exception:
        grade = "A"

    if grade == "B":
        vol_today = float(df["Volume"].iloc[-1])
        vol50_val = float(df["VOL50"].iloc[-1]) if ("VOL50" in df and not pd.isna(df["VOL50"].iloc[-1])) else (float(df["Volume"].iloc[-50:].mean()) if len(df) >= 50 else 0.0)
        has_inst_print = (vol50_val > 0) and (vol_today >= 2.5 * vol50_val)
        has_catalyst = False
        if not (has_catalyst or has_inst_print):
            return None

    # 7 & 8) Entry, Stop Loss, Sizing and Target (via unified calculate_position_risk_parameters)
    entry = float(last_row["Close"])
    atr = float(last_row["ATR14"])
    low_price = float(last_row["Low"]) if "Low" in last_row and not pd.isna(last_row["Low"]) else None

    risk_params = calculate_position_risk_parameters(
        entry=entry,
        atr=atr,
        signal_type=signal_type,
        low_price=low_price,
        capital=CAPITAL,
    )
    if not risk_params:
        return None

    qty = risk_params["Qty"]
    stop = risk_params["Stop"]
    target = risk_params["Target"]
    risk_per_unit = risk_params["Risk Per Unit"]
    risk_amount = risk_params["Risk Amount"]
    gap_qty_applied = risk_params["gap_qty_applied"]

    # Size-aware cap: max_position_value = 0.015 * ADV20_rupees (notional <= 1.5% of avg daily turnover)
    max_position_value = MAX_POSITION_ADV_PCT * adv20_rupees
    if (qty * entry) > max_position_value:
        return None

    risk_amount = qty * risk_per_unit
    sector_sym = SECTOR_MAP.get(symbol, INDEX_SYMBOL)

    rs_map = calculate_rs_rating([symbol])
    rs_val = rs_map.get(symbol)
    base_mat = calculate_base_maturity(df)
    days_base = calculate_days_in_base(df)

    sig_dict = {
        "Signal Date": pd.to_datetime(last_row["Date"]).strftime("%Y-%m-%d"),
        "Symbol": symbol,
        "Sector": sector_sym,
        "Type": signal_type,
        "Close": round(entry, 2),
        "Entry": round(entry, 2),
        "Stop": round(stop, 2),
        "Target": round(target, 2),
        "Qty": int(qty),
        "Risk Per Unit": round(risk_per_unit, 2),
        "Risk Amount": round(risk_amount, 2),
        "ATR14": round(atr, 2),
        "RSI14": round(float(last_row["RSI14"]), 1),
        "catalyst": None,
        "adv20_cr": round(adv20_rupees / 10000000.0, 2),
        "gap_qty_applied": gap_qty_applied,
        "next_earnings": next_earnings,
        "circuit_skipped_reason": circuit_reason,
        "rs_rating": rs_val,
        "base_maturity": base_mat,
        "days_in_base": days_base,
        "inst_footprint": classify_inst_footprint(symbol, df),
        "next_event": get_next_event(symbol, curr_date),
        "warn_event": bool(get_next_event(symbol, curr_date) and 0 <= get_next_event(symbol, curr_date)["days_to_event"] <= 3),
        "mtf_confluence": calculate_mtf_confluence(df, daily_trend_ok=bool(last_row.get("TREND_OK", True))),
    }
    sig_dict["thesis_card"] = build_thesis_card(sig_dict)
    return sig_dict


# =====================================================================
# 8) MESSAGES AND SCANNER RUNNER
# =====================================================================
DISCIPLINE_CARD = (
    "Small-Cap Survival & Risk Rules:\n"
    "• Max 3 concurrent positions | 5% max portfolio heat\n"
    "• 2% daily loss limit | 6% monthly drawdown stop (Elder circuit-breaker)\n"
    "• Worst-case 2-circuit gap sizing enforced (max 2.5% loss on 20% gap)\n"
    "• Position notional capped at <=1.0% of 20-day ADV (min ₹5 Cr ADV)\n"
    "• Fail-closed earnings blackout (5-day window) & circuit proximity skip\n"
    "• 2.5x ATR stop with 9% max stop-loss floor"
)


def format_signal(sig: Dict[str, Any]) -> str:
    """Format signal dictionary into a Telegram alert message."""
    lines = [
        f"🟢 SMALL-CAP SWING SIGNAL ({sig['Type']})",
        f"Symbol: {sig['Symbol']}",
        f"Sector: {sig.get('Sector', 'N/A')}",
        f"Signal Date: {sig['Signal Date']}",
        f"Close: ₹{sig['Close']:.2f}",
        f"Entry: ₹{sig['Entry']:.2f}",
        f"Stop: ₹{sig['Stop']:.2f}",
        f"Target: ₹{sig['Target']:.2f}",
        f"Quantity: {sig['Qty']}",
        f"Risk/Unit: ₹{sig['Risk Per Unit']:.2f}",
        f"Risk Amount: ₹{sig['Risk Amount']:.2f}",
        f"ADV20: ₹{sig.get('adv20_cr', 0.0)} Cr | Gap Sizing: {'YES' if sig.get('gap_qty_applied') else 'NO'}",
        f"Next Earnings: {sig.get('next_earnings', 'N/A')}",
        f"ATR14: {sig['ATR14']:.2f}",
        f"RSI14: {sig['RSI14']:.1f}",
    ]
    return "\n".join(lines)


def run_scanner() -> Tuple[List[Dict[str, Any]], int, bool]:
    """
    Execute the scan across all candidate symbols.
    Returns (signals, scanned_count, is_market_ok).
    """
    print("Checking small-cap regime filter (basket)...")
    is_mkt_ok = regime_ok()
    settings = load_alert_settings()
    is_digest = settings.get("digest", False)

    if not is_mkt_ok:
        msg = "🔴 SMALL-CAP REGIME FILTER (basket): Small-cap basket not in uptrend. No new entries today."
        print(msg)
        if is_digest:
            _DIGEST_MESSAGES.append(("market", msg))
        else:
            send_telegram(msg, kind="proactive", msg_type="market")
        return [], 0, False

    symbols = get_symbols()
    total = len(symbols)
    print(f"Scanning {total} symbols for swing setups...")

    signals: List[Dict[str, Any]] = []
    messages: List[str] = []

    for i, sym in enumerate(symbols, start=1):
        print(f"{i}/{total}: {sym}")
        sig = scan_symbol(sym)
        if sig:
            signals.append(sig)
            formatted = f"{format_signal(sig)}\n\n{DISCIPLINE_CARD}"
            messages.append(formatted)
        time.sleep(0.25)

    if messages:
        joined_message = "\n\n----\n\n".join(messages)
        if is_digest:
            _DIGEST_MESSAGES.append(("scan", joined_message))
        else:
            send_telegram(joined_message, kind="proactive", msg_type="scan")
    elif SEND_NO_SIGNAL_MESSAGE:
        no_sig_msg = "No new small-cap swing signals today."
        if is_digest:
            _DIGEST_MESSAGES.append(("scan", no_sig_msg))
        else:
            send_telegram(no_sig_msg, kind="proactive", msg_type="scan")

    return signals, total, True


# =====================================================================
# 9) WATCHLIST GENERATOR
# =====================================================================
def diagnose(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Diagnose a symbol's trend, coiling status, and breakout proximity.
    """
    df = get_history(symbol)
    if df is None or len(df) < 50:
        return None

    df = add_indicators(df)
    last_row = df.iloc[-1]

    close_val = float(last_row["Close"])
    if "HIGH20" in last_row and not pd.isna(last_row["HIGH20"]):
        high20_val = float(last_row["HIGH20"])
    elif "High" in df.columns and len(df) >= 20:
        high20_val = float(df["High"].iloc[-20:].max())
    else:
        high20_val = close_val

    if pd.isna(close_val) or close_val <= 0 or pd.isna(high20_val):
        return None

    sym_name = symbol[:-3] if symbol.endswith(".NS") else symbol
    sec_sym = SECTOR_MAP.get(symbol, INDEX_SYMBOL)
    sec_ok = sector_ok(symbol)
    sec_bullish = "YES" if sec_ok else "no"
    trend_ok = bool(last_row["TREND_OK"]) if "TREND_OK" in last_row else True
    trend_str = "YES" if trend_ok else "no"
    setup_ok = bool(last_row["SETUP_OK"]) if "SETUP_OK" in last_row else False
    coiling_str = "YES" if setup_ok else "no"
    dist_pct = round(((high20_val - close_val) / close_val) * 100, 2)

    # Composite Setup Score (0-100) & Grade
    #   +25 if TREND_OK
    #   +20 if DistToBreakout% < 2 (scale: 20 * max(0, 1 - dist/5))
    #   +15 if SETUP_OK (coiling today)
    #   +15 if sector_ok(symbol) is True
    #   +10 if VOL_DRYUP
    #   +10 if 40 <= RSI14 <= 65
    #   + 5 if market_ok() else cap the total at 50
    # Clamp to 0-100.
    trend_pts = 25 if trend_ok else 0

    dist = max(0.0, float(dist_pct))
    dist_pts = min(20.0, max(0.0, 20.0 * max(0.0, 1.0 - (dist / 5.0))))

    setup_pts = 15 if setup_ok else 0
    sector_pts = 15 if sec_ok else 0

    vol_dryup = bool(last_row.get("VOL_DRYUP", False))
    vol_pts = 10 if vol_dryup else 0

    rsi_val = last_row.get("RSI14")
    rsi_in_range = False
    if rsi_val is not None and not pd.isna(rsi_val):
        rsi_in_range = (40.0 <= float(rsi_val) <= 65.0)
    rsi_pts = 10 if rsi_in_range else 0

    mkt_ok = bool(market_ok())
    raw_score = trend_pts + dist_pts + setup_pts + sector_pts + vol_pts + rsi_pts
    if mkt_ok:
        raw_score += 5
    else:
        raw_score = min(raw_score, 50.0)

    score = int(round(max(0.0, min(100.0, raw_score))))

    # Grade: A+ if score>=80 and sector bullish and market ok; A if score>=70 and sector bullish; B if score>=60; else C.
    if score >= 80 and sec_ok and mkt_ok:
        grade = "A+"
    elif score >= 70 and sec_ok:
        grade = "A"
    elif score >= 60:
        grade = "B"
    else:
        grade = "C"

    diag_dict = {
        "Symbol": sym_name,
        "Sector": sec_sym,
        "SectorBullish": sec_bullish,
        "Trend": trend_str,
        "Coiling": coiling_str,
        "DistToBreakout%": dist_pct,
        "Close": round(close_val, 2),
        "VolDryup": "YES" if vol_dryup else "no",
        "RsiInRange": "YES" if rsi_in_range else "no",
        "RSI14": round(float(rsi_val), 1) if (rsi_val is not None and not pd.isna(rsi_val)) else None,
        "ATR14": round(float(last_row["ATR14"]), 2) if ("ATR14" in last_row and not pd.isna(last_row["ATR14"])) else None,
        "score": score,
        "grade": grade,
        "Score": score,
        "Grade": grade,
        "rs_rating": calculate_rs_rating([symbol]).get(symbol),
        "base_maturity": calculate_base_maturity(df),
        "days_in_base": calculate_days_in_base(df),
        "inst_footprint": classify_inst_footprint(symbol, df),
        "next_event": get_next_event(symbol, pd.to_datetime(last_row["Date"]).date() if "Date" in last_row else datetime.date.today()),
        "warn_event": bool(
            get_next_event(symbol, pd.to_datetime(last_row["Date"]).date() if "Date" in last_row else datetime.date.today())
            and 0 <= get_next_event(symbol, pd.to_datetime(last_row["Date"]).date() if "Date" in last_row else datetime.date.today())["days_to_event"] <= 3
        ),
        "mtf_confluence": calculate_mtf_confluence(df, daily_trend_ok=trend_ok),
    }
    diag_dict["thesis_card"] = build_thesis_card(diag_dict)
    return diag_dict


def get_watchlist_candidates() -> List[Dict[str, Any]]:
    """
    Scan symbols to build a watchlist of stocks in an uptrend near breakout.
    Returns list of diagnose() dicts with Trend YES and DistToBreakout% <= 5.0,
    sorted by score descending.
    """
    symbols = get_symbols()
    watchlist_candidates: List[Dict[str, Any]] = []

    print("Building watchlist...")
    for sym in symbols:
        diag = diagnose(sym)
        if diag and diag["Trend"] == "YES" and diag["DistToBreakout%"] <= 5.0:
            watchlist_candidates.append(diag)
        time.sleep(0.2)

    # Sort descending by score, secondary ascending by distance to breakout
    watchlist_candidates.sort(key=lambda x: (-x.get("score", 0), x.get("DistToBreakout%", 999.0)))
    return watchlist_candidates


def build_watchlist_text(candidates: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Format watchlist candidates into a readable Telegram message.
    """
    if candidates is None:
        candidates = get_watchlist_candidates()

    if not candidates:
        return "📋 Watchlist empty: no small-cap in uptrend near breakout."

    lines = ["📋 SMALL-CAP WATCHLIST (near breakout)"]
    for item in candidates:
        sec_info = f"{item['Sector']} (Bullish: {item['SectorBullish']})"
        score_val = item.get("score", item.get("Score", "-"))
        grade_val = item.get("grade", item.get("Grade", "-"))
        line = (
            f"{item['Symbol']} [Grade {grade_val} | Score {score_val}] | {sec_info} | "
            f"{item['DistToBreakout%']}% away | Close {item['Close']} | Coiling: {item['Coiling']}"
        )
        lines.append(line)

    return "\n".join(lines)


def compute_market_summary(symbols: Optional[List[str]] = None, history_map: Optional[Dict[str, pd.DataFrame]] = None) -> Dict[str, Any]:
    """
    Computes top-level market summary containing index close/change and universe breadth metrics.
    Keys: source, last_close, prev_close, chg_pct, last_bar_date, as_of_ist,
          breadth_above_sma50, breadth_above_sma200, universe_size, advancers, decliners, unchanged.
    Computed from in-loop history (advancers = last_close > prev_close; graceful zeros on tiny fixture).
    """
    if symbols is None:
        symbols = get_symbols() or []

    # 1. Index / Benchmark metrics
    idx_df = get_cached_index_df()
    if idx_df is None or len(idx_df) < 2:
        idx_df = get_history(INDEX_SYMBOL)

    source = INDEX_SYMBOL
    if idx_df is not None and len(idx_df) >= 2:
        last_close = round(float(idx_df["Close"].iloc[-1]), 2)
        prev_close = round(float(idx_df["Close"].iloc[-2]), 2)
        chg_pct = round(((last_close - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
        last_bar_date = str(pd.to_datetime(idx_df["Date"].iloc[-1]).strftime("%Y-%m-%d")) if "Date" in idx_df else datetime.date.today().strftime("%Y-%m-%d")
    else:
        last_close = 0.0
        prev_close = 0.0
        chg_pct = 0.0
        last_bar_date = datetime.date.today().strftime("%Y-%m-%d")

    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    as_of_ist = datetime.datetime.now(ist_tz).isoformat()

    # 2. Universe breadth and advance/decline metrics
    advancers = 0
    decliners = 0
    unchanged = 0
    above_sma50 = 0
    above_sma200 = 0
    valid_count = 0

    for sym in symbols:
        df = history_map.get(sym) if history_map else get_history(sym)
        if df is None or len(df) < 2:
            continue
        valid_count += 1
        c_last = float(df["Close"].iloc[-1])
        c_prev = float(df["Close"].iloc[-2])
        if c_last > c_prev:
            advancers += 1
        elif c_last < c_prev:
            decliners += 1
        else:
            unchanged += 1

        if len(df) >= 50:
            sma50_val = float(df["SMA50"].iloc[-1]) if ("SMA50" in df and not pd.isna(df["SMA50"].iloc[-1])) else float(df["Close"].rolling(50).mean().iloc[-1])
            if c_last > sma50_val:
                above_sma50 += 1

        if len(df) >= 200:
            sma200_val = float(df["SMA200"].iloc[-1]) if ("SMA200" in df and not pd.isna(df["SMA200"].iloc[-1])) else float(df["Close"].rolling(200).mean().iloc[-1])
            if c_last > sma200_val:
                above_sma200 += 1

    universe_size = len(symbols) if symbols else valid_count
    b_50 = round((above_sma50 / max(1, valid_count)) * 100.0, 1) if valid_count > 0 else 0.0
    b_200 = round((above_sma200 / max(1, valid_count)) * 100.0, 1) if valid_count > 0 else 0.0

    return {
        "source": source,
        "last_close": last_close,
        "prev_close": prev_close,
        "chg_pct": chg_pct,
        "last_bar_date": last_bar_date,
        "as_of_ist": as_of_ist,
        "breadth_above_sma50": b_50,
        "breadth_above_sma200": b_200,
        "universe_size": universe_size,
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": unchanged,
    }


def get_on_deck_candidates(symbols: Optional[List[str]] = None, history_map: Optional[Dict[str, pd.DataFrame]] = None) -> List[Dict[str, Any]]:
    """
    Identify up-to-5 symbols passing TREND_OK & SETUP_OK & sector_ok but failing BREAKOUT or VOL_SPIKE.
    Each item: {symbol, close, breakout_level, dist_pct, missing_condition, atr14, rsi14}.
    Sorted by dist_pct ascending.
    """
    if symbols is None:
        symbols = get_symbols() or []

    candidates: List[Dict[str, Any]] = []
    for sym in symbols:
        df = history_map.get(sym) if history_map else get_history(sym)
        if df is None or len(df) < 50:
            continue
        try:
            df_ind = add_indicators(df)
            last_row = df_ind.iloc[-1]
            trend_ok = bool(last_row.get("TREND_OK", False))
            setup_ok = bool(last_row.get("SETUP_OK", False))
            sec_ok = sector_ok(sym)

            if trend_ok and setup_ok and sec_ok:
                is_breakout = bool(last_row.get("BREAKOUT", False))
                is_vol_spike = bool(last_row.get("VOL_SPIKE", False))

                if not (is_breakout and is_vol_spike):
                    if not is_breakout and not is_vol_spike:
                        missing = "BREAKOUT, VOL_SPIKE"
                    elif not is_breakout:
                        missing = "BREAKOUT"
                    else:
                        missing = "VOL_SPIKE"

                    c = round(float(last_row["Close"]), 2)
                    high20 = float(last_row.get("HIGH20", df["High"].iloc[-20:].max()))
                    if pd.isna(high20) or high20 <= 0:
                        high20 = c
                    dist_pct = round(((high20 - c) / c) * 100.0, 2)
                    atr14 = round(float(last_row["ATR14"]), 2) if ("ATR14" in last_row and not pd.isna(last_row["ATR14"])) else None
                    rsi14 = round(float(last_row["RSI14"]), 1) if ("RSI14" in last_row and not pd.isna(last_row["RSI14"])) else None

                    c_date = pd.to_datetime(last_row["Date"]).date() if "Date" in last_row else datetime.date.today()
                    n_ev = get_next_event(sym, c_date)

                    od_item = {
                        "symbol": sym,
                        "close": c,
                        "breakout_level": round(high20, 2),
                        "dist_pct": dist_pct,
                        "missing_condition": missing,
                        "atr14": atr14,
                        "rsi14": rsi14,
                        "inst_footprint": classify_inst_footprint(sym, df),
                        "next_event": n_ev,
                        "warn_event": bool(n_ev and 0 <= n_ev["days_to_event"] <= 3),
                        "mtf_confluence": calculate_mtf_confluence(df, daily_trend_ok=bool(last_row.get("TREND_OK", False))),
                    }
                    od_item["thesis_card"] = build_thesis_card(od_item)
                    candidates.append(od_item)
        except Exception:
            continue

    candidates.sort(key=lambda x: x["dist_pct"])
    return candidates[:5]


def get_leaders_board(symbols: Optional[List[str]] = None, history_map: Optional[Dict[str, pd.DataFrame]] = None) -> List[Dict[str, Any]]:
    """
    Up-to-10 highest rs_rating symbols that are also in Stage-2 (TREND_OK).
    Returns list of dicts with symbol, rs_rating, close, sector, sorted by rs_rating descending.
    """
    if symbols is None:
        symbols = get_symbols() or []

    rs_map = calculate_rs_rating(symbols, history_map=history_map)
    leaders: List[Dict[str, Any]] = []

    for sym in symbols:
        rs = rs_map.get(sym)
        if rs is None:
            continue
        df = history_map.get(sym) if history_map else get_history(sym)
        if df is None or len(df) < 50:
            continue
        try:
            df_ind = add_indicators(df)
            last_row = df_ind.iloc[-1]
            if bool(last_row.get("TREND_OK", False)):
                c = round(float(last_row["Close"]), 2)
                sec = SECTOR_MAP.get(sym, INDEX_SYMBOL)
                leaders.append({
                    "symbol": sym,
                    "rs_rating": rs,
                    "close": c,
                    "sector": sec,
                })
        except Exception:
            continue

    leaders.sort(key=lambda x: (-x["rs_rating"], x["symbol"]))
    return leaders[:10]


# =====================================================================
# 10) TRADING JOURNAL & TELEGRAM BOT COMMANDS
# =====================================================================
def load_json_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Safely load a list of dictionaries from a JSON file.
    Creates an empty JSON file with [] if missing.
    """
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("[]\n")
        except Exception as exc:
            print(f"Error creating default {file_path}: {exc}")
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            data = json.loads(content)
            if isinstance(data, list):
                return data
            return []
    except Exception as exc:
        print(f"Error loading {file_path}: {exc}")
        return []


def save_json_file(file_path: str, data: List[Dict[str, Any]]) -> None:
    """Safely save a list of dictionaries to a JSON file."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Error saving {file_path}: {exc}")


def load_trades() -> List[Dict[str, Any]]:
    """Load all closed trades from trades.json."""
    return load_json_file(TRADES_FILE)


def save_trades(data: List[Dict[str, Any]]) -> None:
    """Save closed trades to trades.json."""
    save_json_file(TRADES_FILE, data)


def load_open_positions() -> List[Dict[str, Any]]:
    """Load all open positions from open_positions.json."""
    return load_json_file(OPEN_POSITIONS_FILE)


def save_open_positions(data: List[Dict[str, Any]]) -> None:
    """Save open positions to open_positions.json."""
    save_json_file(OPEN_POSITIONS_FILE, data)


def compute_portfolio_heat(
    open_positions: List[Dict[str, Any]],
    capital: float = CAPITAL,
    max_heat_pct: float = MAX_TOTAL_HEAT_PCT
) -> Dict[str, Any]:
    """
    Computes portfolio heat gauge metrics across all open positions.
    Total open risk = sum((entry - stop) * qty).
    Heat percentage = total_risk / capital.
    Heat gauge percentage = total_risk / (max_heat_pct * capital) * 100%.
    Status:
      - green: < 60%
      - amber: 60% - 90%
      - red: > 90%
    """
    total_risk = 0.0
    position_heats = []

    for pos in open_positions:
        sym = pos.get("symbol", "")
        entry = float(pos.get("entry_price") or pos.get("entry") or 0.0)
        qty = float(pos.get("qty") or 0.0)
        stop = pos.get("stop")
        if stop is not None and float(stop) > 0 and entry > float(stop):
            risk_unit = entry - float(stop)
        else:
            risk_unit = entry * 0.05
        pos_risk = risk_unit * qty
        total_risk += pos_risk

        pct_capital = (pos_risk / capital * 100.0) if capital > 0 else 0.0
        position_heats.append({
            "symbol": sym,
            "entry": round(entry, 2),
            "qty": int(qty),
            "stop": round(float(stop), 2) if stop is not None else None,
            "risk_inr": round(pos_risk, 2),
            "risk_pct_capital": round(pct_capital, 2),
        })

    max_heat_budget = max_heat_pct * capital
    heat_pct = (total_risk / capital * 100.0) if capital > 0 else 0.0
    gauge_pct = (total_risk / max_heat_budget * 100.0) if max_heat_budget > 0 else 0.0

    if gauge_pct < 60.0:
        heat_status = "green"
    elif gauge_pct <= 90.0:
        heat_status = "amber"
    else:
        heat_status = "red"

    return {
        "total_risk": round(total_risk, 2),
        "capital": capital,
        "max_heat_budget": round(max_heat_budget, 2),
        "heat_pct": round(heat_pct, 2),
        "gauge_pct": round(gauge_pct, 1),
        "heat_status": heat_status,
        "positions": position_heats,
    }


def compute_live_journal_stats(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculates live trading journal performance statistics from closed trades.
    Includes win rate, avg win/loss R, expectancy R, profit factor, max drawdown,
    best/worst trades, breakdowns by grade, signal_type, and exit_reason,
    and tails captured percentage (winners extending past +2R).
    """
    if not trades:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "profit_factor": 0.0,
            "avg_win_r": 0.0,
            "avg_loss_r": 0.0,
            "expectancy_r": 0.0,
            "max_drawdown": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "tails_captured_pct": 0.0,
            "by_grade": {},
            "by_signal_type": {},
            "by_exit_reason": {},
        }

    total_trades = len(trades)
    wins = [t for t in trades if float(t.get("pnl") or 0.0) > 0]
    losses = [t for t in trades if float(t.get("pnl") or 0.0) <= 0]

    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    sum_wins_pnl = sum(float(t.get("pnl") or 0.0) for t in wins)
    sum_losses_pnl = sum(float(t.get("pnl") or 0.0) for t in losses)
    total_pnl = sum_wins_pnl + sum_losses_pnl

    if sum_losses_pnl != 0:
        profit_factor = round(sum_wins_pnl / abs(sum_losses_pnl), 2)
    elif sum_wins_pnl > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0

    # R-Multiple calculations
    win_rs = []
    for t in wins:
        if t.get("r_multiple") is not None:
            win_rs.append(float(t["r_multiple"]))
        elif t.get("exit_price") and t.get("entry_price") and t.get("stop"):
            risk = float(t["entry_price"]) - float(t["stop"])
            if risk > 0:
                win_rs.append((float(t["exit_price"]) - float(t["entry_price"])) / risk)

    loss_rs = []
    for t in losses:
        if t.get("r_multiple") is not None:
            loss_rs.append(float(t["r_multiple"]))
        elif t.get("exit_price") and t.get("entry_price") and t.get("stop"):
            risk = float(t["entry_price"]) - float(t["stop"])
            if risk > 0:
                loss_rs.append((float(t["exit_price"]) - float(t["entry_price"])) / risk)

    avg_win_r = round(sum(win_rs) / len(win_rs), 2) if win_rs else 0.0
    avg_loss_r = round(sum(loss_rs) / len(loss_rs), 2) if loss_rs else 0.0

    win_prob = len(wins) / total_trades if total_trades > 0 else 0.0
    loss_prob = 1.0 - win_prob
    expectancy_r = round((win_prob * avg_win_r) - (loss_prob * abs(avg_loss_r)), 2)

    # Chronological Max Drawdown
    sorted_trades = sorted(trades, key=lambda x: str(x.get("exit_date") or x.get("entry_date") or ""))
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted_trades:
        cum += float(t.get("pnl") or 0.0)
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    pnls = [float(t.get("pnl") or 0.0) for t in trades]
    best_trade = round(max(pnls), 2) if pnls else 0.0
    worst_trade = round(min(pnls), 2) if pnls else 0.0

    # Tails Captured (% winners running past +2R via trailing stop)
    tails_count = 0
    for t in wins:
        r_val = float(t.get("r_multiple") or 0.0)
        reason = str(t.get("exit_reason") or t.get("reason") or "").lower()
        if r_val >= 2.0 or "trail" in reason:
            tails_count += 1
    tails_captured_pct = round((tails_count / len(wins) * 100.0) if wins else 0.0, 1)

    # Breakdowns by grade, signal_type, exit_reason
    by_grade: Dict[str, Dict[str, Any]] = {}
    by_signal: Dict[str, Dict[str, Any]] = {}
    by_exit: Dict[str, Dict[str, Any]] = {}

    for t in trades:
        g = str(t.get("grade") or t.get("Grade") or "Unknown").upper()
        if g not in by_grade:
            by_grade[g] = {"count": 0, "wins": 0, "pnl": 0.0}
        by_grade[g]["count"] += 1
        p = float(t.get("pnl") or 0.0)
        by_grade[g]["pnl"] += p
        if p > 0:
            by_grade[g]["wins"] += 1

        st = str(t.get("signal_type") or t.get("type") or "BREAKOUT").upper()
        if st not in by_signal:
            by_signal[st] = {"count": 0, "wins": 0, "pnl": 0.0}
        by_signal[st]["count"] += 1
        by_signal[st]["pnl"] += p
        if p > 0:
            by_signal[st]["wins"] += 1

        er = str(t.get("exit_reason") or t.get("reason") or "MANUAL").upper()
        if er not in by_exit:
            by_exit[er] = {"count": 0, "wins": 0, "pnl": 0.0}
        by_exit[er]["count"] += 1
        by_exit[er]["pnl"] += p
        if p > 0:
            by_exit[er]["wins"] += 1

    for d in (by_grade, by_signal, by_exit):
        for k, v in d.items():
            cnt = v["count"]
            v["win_rate"] = round((v["wins"] / cnt * 100.0) if cnt > 0 else 0.0, 1)
            v["pnl"] = round(v["pnl"], 2)

    return {
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "profit_factor": profit_factor,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "expectancy_r": expectancy_r,
        "max_drawdown": round(max_dd, 2),
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "tails_captured_pct": tails_captured_pct,
        "by_grade": by_grade,
        "by_signal_type": by_signal,
        "by_exit_reason": by_exit,
    }


def get_updates(offset: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Call Telegram getUpdates API with the bot token and an optional offset.
    Returns the list of update objects.
    """
    if not TELEGRAM_BOT_TOKEN:
        return []
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params: Dict[str, Any] = {"timeout": 10}
    if offset is not None:
        params["offset"] = offset

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
    except Exception as exc:
        print(f"Error calling Telegram getUpdates: {exc}")
    return []


def handle_command(text: str, chat_id: Any = None) -> Optional[str]:
    """
    Parse and process journal commands received from Telegram.
    Security: Only responds to messages originating from the configured TELEGRAM_CHAT_ID.
    Case-insensitive, supports bot username mentions (e.g. /buy@my_bot).
    """
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID

    if not TELEGRAM_CHAT_ID or str(chat_id).strip() != str(TELEGRAM_CHAT_ID).strip():
        print(f"Ignored unauthorized message from chat_id: {chat_id}")
        return None

    cleaned_text = text.strip()
    if not cleaned_text.startswith("/"):
        return None

    parts = cleaned_text.split()
    if not parts:
        return None

    # Strip bot username suffix if present e.g. /buy@bot -> /buy
    cmd = parts[0].lower().split("@")[0]
    args = parts[1:]

    try:
        if cmd == "/help":
            return (
                "🤖 SWING TRADING BOT COMMANDS:\n\n"
                "• /buy SYMBOL ENTRY QTY [STOP] [TARGET] [#tags...]\n"
                "  Record a new open swing trade position.\n"
                "  Example: /buy PERSISTENT 5200 10 4950 5700 #breakout #plan_followed\n\n"
                "• /sell SYMBOL EXIT [NOTE] [#tags...]\n"
                "  Close an open position and log PnL & discipline audit.\n"
                "  Example: /sell PERSISTENT 5600 hit target 2R #plan_followed\n\n"
                "• /open\n"
                "  List all current open swing positions.\n"
                "  Example: /open\n\n"
                "• /trades\n"
                "  List the last 10 closed trades with tags & notes.\n"
                "  Example: /trades\n\n"
                "• /stats\n"
                "  View journal metrics: win rate, expectancy, drawdown & discipline.\n"
                "  Example: /stats\n\n"
                "• /mute [duration]\n"
                "  Temporarily silence all alerts and command replies (default 8h).\n"
                "  Example: /mute 4h (or: /mute 30m, /mute until 07:00)\n\n"
                "• /unmute\n"
                "  Cancel active mute and restore alerts immediately.\n"
                "  Example: /unmute\n\n"
                "• /quiet START END | /quiet off\n"
                "  Set daily quiet window (HH:MM IST) or disable it.\n"
                "  Example: /quiet 21:00 08:00 (or: /quiet off)\n\n"
                "• /alerts [scan|watchlist|market|digest on|off]\n"
                "  View alert configuration or toggle specific alert channels.\n"
                "  Example: /alerts (or: /alerts scan off, /alerts digest on)\n\n"
                "• /help\n"
                "  Show this commands help menu.\n"
                "  Example: /help"
            )

        elif cmd == "/buy":
            # Usage: /buy SYMBOL ENTRY_PRICE QTY [STOP] [TARGET] [#tag1 #tag2 ...]
            tags = [arg.strip() for arg in args if arg.strip().startswith("#")]
            non_tag_args = [arg for arg in args if not arg.strip().startswith("#")]

            if len(non_tag_args) < 3:
                return "⚠️ Usage: /buy SYMBOL ENTRY_PRICE QTY [STOP] [TARGET] [#tag1 #tag2 ...]\nExample: /buy PERSISTENT 5200 10 4950 5700 #breakout #plan_followed"

            raw_sym = non_tag_args[0].strip().upper()
            sym = raw_sym if raw_sym.endswith(".NS") else f"{raw_sym}.NS"

            try:
                entry_price = float(non_tag_args[1])
                qty = int(float(non_tag_args[2]))
            except ValueError:
                return "⚠️ Invalid format: Entry price and quantity must be valid numbers."

            if entry_price <= 0 or qty <= 0:
                return "⚠️ Entry price and quantity must be positive numbers."

            stop = None
            target = None
            if len(non_tag_args) >= 4:
                try:
                    stop = float(non_tag_args[3])
                except ValueError:
                    return "⚠️ Invalid format: Stop loss must be a number."
            if len(non_tag_args) >= 5:
                try:
                    target = float(non_tag_args[4])
                except ValueError:
                    return "⚠️ Invalid format: Target price must be a number."

            # Enforce small-cap survival risk, heat and drawdown limits
            limit_err = check_buy_limits(sym, entry_price, qty, stop)
            if limit_err:
                return limit_err

            open_positions = load_open_positions()
            today_str = datetime.date.today().isoformat()

            new_pos = {
                "symbol": sym,
                "entry_date": today_str,
                "entry_price": round(entry_price, 2),
                "qty": qty,
                "stop": round(stop, 2) if stop is not None else None,
                "planned_stop": round(stop, 2) if stop is not None else None,
                "target": round(target, 2) if target is not None else None,
                "tags": tags,
            }
            open_positions.append(new_pos)
            save_open_positions(open_positions)

            stop_str = f"₹{stop:,.2f}" if stop is not None else "None"
            target_str = f"₹{target:,.2f}" if target is not None else "None"
            tags_line = f"\nTags: {' '.join(tags)}" if tags else ""

            return (
                f"✅ POSITION OPENED:\n"
                f"Symbol: {sym}\n"
                f"Entry: ₹{entry_price:,.2f} | Qty: {qty}\n"
                f"Stop: {stop_str} | Target: {target_str}\n"
                f"Date: {today_str}"
                f"{tags_line}"
            )

        elif cmd == "/sell":
            # Usage: /sell SYMBOL EXIT_PRICE [NOTE] [#tag1 #tag2 ...]
            sell_tags = [arg.strip() for arg in args if arg.strip().startswith("#")]
            non_tag_args = [arg for arg in args if not arg.strip().startswith("#")]

            if len(non_tag_args) < 2:
                return "⚠️ Usage: /sell SYMBOL EXIT_PRICE [NOTE] [#tag1 #tag2 ...]\nExample: /sell PERSISTENT 5600 Exited at 2R target #plan_followed"

            raw_sym = non_tag_args[0].strip().upper()
            search_sym = raw_sym[:-3] if raw_sym.endswith(".NS") else raw_sym

            try:
                exit_price = float(non_tag_args[1])
            except ValueError:
                return "⚠️ Invalid format: Exit price must be a valid number."

            note = " ".join(non_tag_args[2:]).strip() if len(non_tag_args) > 2 else ""

            open_positions = load_open_positions()
            matched_idx = -1
            matched_pos = None

            for i, pos in enumerate(open_positions):
                pos_sym = pos["symbol"].upper()
                pos_clean = pos_sym[:-3] if pos_sym.endswith(".NS") else pos_sym
                if pos_clean == search_sym:
                    matched_idx = i
                    matched_pos = pos
                    break

            if matched_pos is None:
                return f"❌ No open position found for {raw_sym}. Use /open to view active positions."

            # Remove from open positions
            open_positions.pop(matched_idx)
            save_open_positions(open_positions)

            entry_price = float(matched_pos["entry_price"])
            qty = int(matched_pos["qty"])
            entry_date = matched_pos.get("entry_date", datetime.date.today().isoformat())
            stop_val = matched_pos.get("stop")
            planned_stop = matched_pos.get("planned_stop", stop_val)
            target_val = matched_pos.get("target")

            pnl = (exit_price - entry_price) * qty
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

            r_mult = None
            if stop_val is not None:
                risk_per_unit = entry_price - float(stop_val)
                if abs(risk_per_unit) > 1e-4:
                    r_mult = (exit_price - entry_price) / risk_per_unit

            today_str = datetime.date.today().isoformat()

            # Holding period calculation
            holding_days = 0
            try:
                d_entry = datetime.date.fromisoformat(str(entry_date)[:10])
                d_exit = datetime.date.fromisoformat(str(today_str)[:10])
                holding_days = (d_exit - d_entry).days
            except Exception:
                holding_days = 0

            # Tags handling (combine buy tags and sell tags without duplicates)
            pos_tags = matched_pos.get("tags") or []
            if not isinstance(pos_tags, list):
                pos_tags = []
            combined_tags = list(dict.fromkeys(pos_tags + sell_tags))

            # Mistake tracking
            # 1) If exit price is worse than planned_stop: "stop_moved"
            # 2) If held more than 5 days with return under 3%: "time_stop_ignored"
            # 3) Otherwise mistake is null
            mistake = None
            planned_stop_num = None
            if planned_stop is not None:
                try:
                    planned_stop_num = float(planned_stop)
                except (ValueError, TypeError):
                    planned_stop_num = None

            if planned_stop_num is not None and exit_price < planned_stop_num:
                mistake = "stop_moved"
            elif holding_days > 5 and pnl_pct < 3.0:
                mistake = "time_stop_ignored"

            closed_trade = {
                "symbol": matched_pos["symbol"],
                "entry_date": entry_date,
                "entry_price": round(entry_price, 2),
                "qty": qty,
                "stop": round(float(stop_val), 2) if stop_val is not None else None,
                "planned_stop": round(planned_stop_num, 2) if planned_stop_num is not None else None,
                "target": round(float(target_val), 2) if target_val is not None else None,
                "exit_date": today_str,
                "exit_price": round(exit_price, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "r_multiple": round(r_mult, 2) if r_mult is not None else None,
                "note": note,
                "tags": combined_tags,
                "mistake": mistake,
            }

            trades = load_trades()
            trades.append(closed_trade)
            save_trades(trades)

            sign = "+" if pnl >= 0 else ""
            r_str = f"{r_mult:+.2f}R" if r_mult is not None else "N/A"
            note_str = f"\nNote: {note}" if note else ""
            tags_str = f"\nTags: {' '.join(combined_tags)}" if combined_tags else ""
            mistake_str = f"\n⚠️ Mistake: {mistake}" if mistake else ""

            return (
                f"🎯 POSITION CLOSED:\n"
                f"Symbol: {closed_trade['symbol']}\n"
                f"Entry: ₹{entry_price:,.2f} ({entry_date}) -> Exit: ₹{exit_price:,.2f} ({today_str})\n"
                f"Qty: {qty}\n"
                f"PnL: {sign}₹{pnl:,.2f} ({sign}{pnl_pct:.2f}%)\n"
                f"R-Multiple: {r_str}"
                f"{note_str}"
                f"{tags_str}"
                f"{mistake_str}"
            )

        elif cmd == "/open":
            positions = load_open_positions()
            if not positions:
                return "📋 No open positions currently."

            lines = [f"📋 OPEN POSITIONS ({len(positions)}):"]
            for i, p in enumerate(positions, start=1):
                sym_clean = p["symbol"]
                e_price = p["entry_price"]
                q = p["qty"]
                e_date = p.get("entry_date", "N/A")
                s_str = f"₹{p['stop']:,.2f}" if p.get("stop") is not None else "None"
                t_str = f"₹{p['target']:,.2f}" if p.get("target") is not None else "None"
                tags_str = f" | Tags: {' '.join(p['tags'])}" if p.get("tags") else ""
                lines.append(f"{i}) {sym_clean} (Qty: {q}){tags_str}")
                lines.append(f"   Entry: ₹{e_price:,.2f} on {e_date}")
                lines.append(f"   Stop: {s_str} | Target: {t_str}")

            return "\n".join(lines)

        elif cmd == "/trades":
            trades = load_trades()
            if not trades:
                return "📜 No closed trades recorded yet."

            recent = trades[-10:]
            recent.reverse()  # most recent first

            lines = [f"📜 RECENT CLOSED TRADES (Last {len(recent)}):"]
            for t in recent:
                pnl = t["pnl"]
                sign = "+" if pnl >= 0 else ""
                r_str = f"{t['r_multiple']:+.2f}R" if t.get("r_multiple") is not None else "N/A"
                tag_line = f" | Tags: {' '.join(t.get('tags', []))}" if t.get("tags") else ""
                mistake_line = f" | ⚠️ {t.get('mistake')}" if t.get("mistake") else ""
                lines.append(
                    f"• {t['symbol']}: {sign}₹{pnl:,.2f} ({sign}{t['pnl_pct']:.1f}%) | R: {r_str}{tag_line}{mistake_line}\n"
                    f"  Entry: ₹{t['entry_price']:,.2f} ({t['entry_date']}) -> Exit: ₹{t['exit_price']:,.2f} ({t['exit_date']})"
                )
                if t.get("note"):
                    lines.append(f"  Note: {t['note']}")

            return "\n".join(lines)

        elif cmd == "/stats":
            trades = load_trades()
            if not trades:
                return "📊 No closed trades available to calculate statistics."

            total_trades = len(trades)
            wins = [t for t in trades if t["pnl"] > 0]
            losses = [t for t in trades if t["pnl"] <= 0]

            win_rate = (len(wins) / total_trades) * 100.0
            avg_win = (sum(t["pnl"] for t in wins) / len(wins)) if wins else 0.0
            avg_loss = (sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0
            sum_wins = sum(t["pnl"] for t in wins)
            sum_losses = sum(t["pnl"] for t in losses)

            if sum_losses != 0:
                profit_factor = sum_wins / abs(sum_losses)
                pf_str = f"{profit_factor:.2f}"
            elif sum_wins > 0:
                pf_str = "∞ (All Wins)"
            else:
                pf_str = "0.00"

            win_prob = len(wins) / total_trades
            loss_prob = 1.0 - win_prob
            expectancy = (win_prob * avg_win) - (loss_prob * abs(avg_loss))
            total_pnl = sum(t["pnl"] for t in trades)

            best_trade = max((t["pnl"] for t in trades), default=0.0)
            worst_trade = min((t["pnl"] for t in trades), default=0.0)

            # Max drawdown on cumulative PnL
            cum = 0.0
            peak = 0.0
            max_dd = 0.0
            for t in trades:
                cum += t["pnl"]
                if cum > peak:
                    peak = cum
                dd = peak - cum
                if dd > max_dd:
                    max_dd = dd

            pnl_sign = "+" if total_pnl >= 0 else ""
            exp_sign = "+" if expectancy >= 0 else ""
            best_sign = "+" if best_trade >= 0 else ""
            worst_sign = "+" if worst_trade >= 0 else ""

            # Tag & Mistake stats
            breakout_trades = [t for t in trades if "#breakout" in [tag.lower() for tag in (t.get("tags") or [])]]
            pullback_trades = [t for t in trades if "#pullback" in [tag.lower() for tag in (t.get("tags") or [])]]
            plan_trades = [t for t in trades if "#plan_followed" in [tag.lower() for tag in (t.get("tags") or [])]]
            mistake_trades = [t for t in trades if t.get("mistake")]

            breakout_wr = (len([t for t in breakout_trades if t["pnl"] > 0]) / len(breakout_trades) * 100) if breakout_trades else 0.0
            pullback_wr = (len([t for t in pullback_trades if t["pnl"] > 0]) / len(pullback_trades) * 100) if pullback_trades else 0.0
            plan_wr = (len([t for t in plan_trades if t["pnl"] > 0]) / len(plan_trades) * 100) if plan_trades else 0.0

            discipline_lines = [
                f"\n🎯 SETUP & DISCIPLINE AUDIT:",
                f"• #breakout Win Rate: {breakout_wr:.1f}% ({len(breakout_trades)} trades)" if breakout_trades else "• #breakout: 0 trades",
                f"• #pullback Win Rate: {pullback_wr:.1f}% ({len(pullback_trades)} trades)" if pullback_trades else "• #pullback: 0 trades",
                f"• #plan_followed Win Rate: {plan_wr:.1f}% ({len(plan_trades)} trades)" if plan_trades else "• #plan_followed: 0 trades",
                f"• Recorded Mistakes: {len(mistake_trades)}"
            ]

            return (
                "📊 SWING JOURNAL PERFORMANCE:\n\n"
                f"• Total Trades: {total_trades} (Wins: {len(wins)}, Losses: {len(losses)})\n"
                f"• Win Rate: {win_rate:.1f}%\n"
                f"• Total PnL: {pnl_sign}₹{total_pnl:,.2f}\n"
                f"• Profit Factor: {pf_str}\n"
                f"• Expectancy / Trade: {exp_sign}₹{expectancy:,.2f}\n"
                f"• Average Win: +₹{avg_win:,.2f}\n"
                f"• Average Loss: -₹{abs(avg_loss):,.2f}\n"
                f"• Max Drawdown: ₹{max_dd:,.2f}\n"
                f"• Best Trade: {best_sign}₹{best_trade:,.2f}\n"
                f"• Worst Trade: {worst_sign}₹{worst_trade:,.2f}\n"
                + "\n".join(discipline_lines)
            )

        elif cmd == "/mute":
            # Usage: /mute [duration] e.g. /mute 4h, /mute 30m, /mute until 07:00; default 8h.
            settings = load_alert_settings()
            now_ist = get_now_ist()
            arg_str = " ".join(args).strip().lower()

            target_dt = None
            if not arg_str:
                target_dt = now_ist + datetime.timedelta(hours=8)
            elif arg_str.startswith("until"):
                time_str = arg_str.replace("until", "").strip()
                match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
                if not match:
                    return "⚠️ Invalid format for /mute until. Example: /mute until 07:00"
                h, m = int(match.group(1)), int(match.group(2))
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    return "⚠️ Invalid time: Hour must be 00-23, minute 00-59."
                target_dt = now_ist.replace(hour=h, minute=m, second=0, microsecond=0)
                if target_dt <= now_ist:
                    target_dt += datetime.timedelta(days=1)
            else:
                match = re.match(r"^(\d+(?:\.\d+)?)\s*(h|m|d)$", arg_str)
                if match:
                    val = float(match.group(1))
                    unit = match.group(2)
                    if unit == "h":
                        target_dt = now_ist + datetime.timedelta(hours=val)
                    elif unit == "m":
                        target_dt = now_ist + datetime.timedelta(minutes=val)
                    elif unit == "d":
                        target_dt = now_ist + datetime.timedelta(days=val)
                else:
                    return "⚠️ Invalid mute duration. Examples: /mute 4h, /mute 30m, /mute until 07:00, or /mute (defaults to 8h)"

            settings["mute_until"] = target_dt.isoformat()
            save_alert_settings(settings)
            formatted_time = target_dt.strftime("%H:%M IST (%d %b)")
            return f"Muted until {formatted_time}. /unmute to cancel."

        elif cmd == "/unmute":
            settings = load_alert_settings()
            settings["mute_until"] = None
            save_alert_settings(settings)
            return "🔔 Unmuted. Alerts and replies restored."

        elif cmd == "/quiet":
            # Usage: /quiet START END (e.g. /quiet 21:00 08:00) or /quiet off
            settings = load_alert_settings()
            if not args:
                q_s = settings.get("quiet_start")
                q_e = settings.get("quiet_end")
                if q_s and q_e and q_s != "off" and q_e != "off":
                    return f"🌙 Current quiet window: {q_s} - {q_e} IST.\nUsage: /quiet START END (e.g. /quiet 21:00 08:00) or /quiet off"
                return "🌙 Quiet window is currently disabled.\nUsage: /quiet START END (e.g. /quiet 21:00 08:00)"

            if len(args) == 1 and args[0].lower() == "off":
                settings["quiet_start"] = "off"
                settings["quiet_end"] = "off"
                save_alert_settings(settings)
                return "🌙 Quiet window disabled. Proactive alerts allowed at any hour."

            if len(args) == 2:
                start_raw, end_raw = args[0].strip(), args[1].strip()
                time_pat = r"^([01]?\d|2[0-3]):([0-5]\d)$"
                m_start = re.match(time_pat, start_raw)
                m_end = re.match(time_pat, end_raw)
                if not m_start or not m_end:
                    return "⚠️ Invalid format: /quiet START END must use HH:MM (e.g. /quiet 21:00 08:00) or /quiet off"

                start_str = f"{int(m_start.group(1)):02d}:{m_start.group(2)}"
                end_str = f"{int(m_end.group(1)):02d}:{m_end.group(2)}"

                settings["quiet_start"] = start_str
                settings["quiet_end"] = end_str
                save_alert_settings(settings)
                return f"🌙 Quiet window set to {start_str} - {end_str} IST."

            return "⚠️ Usage: /quiet START END (e.g. /quiet 21:00 08:00) or /quiet off"

        elif cmd == "/alerts":
            # Usage:
            # /alerts -> show current status
            # /alerts scan on|off
            # /alerts watchlist on|off
            # /alerts market on|off
            # /alerts digest on|off
            settings = load_alert_settings()

            if not args:
                now_ist = get_now_ist()
                mute_str = "Off (not muted)"
                mute_until_val = settings.get("mute_until")
                if mute_until_val:
                    try:
                        mute_dt = datetime.datetime.fromisoformat(mute_until_val)
                        if mute_dt.tzinfo is None:
                            mute_dt = mute_dt.replace(tzinfo=IST_TZ)
                        if now_ist < mute_dt:
                            mute_str = f"Muted until {mute_dt.strftime('%H:%M IST (%d %b)')}"
                    except Exception:
                        pass

                q_s = settings.get("quiet_start")
                q_e = settings.get("quiet_end")
                if q_s and q_e and q_s != "off" and q_e != "off":
                    quiet_str = f"{q_s} - {q_e} IST"
                else:
                    quiet_str = "Disabled (proactive alerts allowed any hour)"

                quiet_env_active = (os.getenv("QUIET", "0").strip() == "1")
                quiet_env_str = "ACTIVE (forcing silence)" if quiet_env_active else "Inactive"

                en = settings.get("enable", {})
                scan_en = "ON" if en.get("scan", True) else "OFF"
                wl_en = "ON" if en.get("watchlist", True) else "OFF"
                mkt_en = "ON" if en.get("market", True) else "OFF"
                digest_en = "ON" if settings.get("digest", False) else "OFF"

                return (
                    "⚙️ TELEGRAM ALERT SETTINGS:\n\n"
                    f"• Mute State: {mute_str}\n"
                    f"• Quiet Window: {quiet_str}\n"
                    f"• QUIET Env: {quiet_env_str}\n"
                    f"• Scan Alerts: {scan_en}\n"
                    f"• Watchlist Alerts: {wl_en}\n"
                    f"• Market Alerts: {mkt_en}\n"
                    f"• Digest Mode: {digest_en}\n\n"
                    "Commands to modify:\n"
                    "• /mute [duration] | /unmute\n"
                    "• /quiet START END | /quiet off\n"
                    "• /alerts scan on|off\n"
                    "• /alerts watchlist on|off\n"
                    "• /alerts market on|off\n"
                    "• /alerts digest on|off"
                )

            subcmd = args[0].lower()
            if len(args) < 2:
                return "⚠️ Usage: /alerts scan on|off, /alerts watchlist on|off, /alerts market on|off, /alerts digest on|off"

            state_val = args[1].lower()
            if state_val not in ("on", "off"):
                return f"⚠️ Invalid option '{args[1]}': choose 'on' or 'off'."

            bool_val = (state_val == "on")

            if subcmd in ("scan", "watchlist", "market"):
                if "enable" not in settings or not isinstance(settings["enable"], dict):
                    settings["enable"] = dict(DEFAULT_ALERT_SETTINGS["enable"])
                settings["enable"][subcmd] = bool_val
                save_alert_settings(settings)
                status_icon = "✅" if bool_val else "⏸️"
                return f"{status_icon} Alerts for '{subcmd}' set to {state_val.upper()}."

            elif subcmd == "digest":
                settings["digest"] = bool_val
                save_alert_settings(settings)
                status_icon = "✅" if bool_val else "⏸️"
                desc = "evening alerts combined into 1 message" if bool_val else "alerts sent individually"
                return f"{status_icon} Digest mode set to {state_val.upper()} ({desc})."

            else:
                return f"⚠️ Unknown alerts sub-command: '{subcmd}'. Choose scan, watchlist, market, or digest."

        else:
            return f"❓ Unknown command: {cmd}\nType /help to see all available commands."

    except Exception as exc:
        print(f"Error handling command '{text}': {exc}")
        return f"⚠️ Error processing command: {exc}"


def handle_telegram_command(text: str, chat_id: Any = None) -> Optional[str]:
    """Convenience alias for command processing in tests and CLI."""
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID or "987654321"
    return handle_command(text, chat_id)


def select_new_updates(
    updates: List[Dict[str, Any]],
    offset: Optional[int]
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """
    Pure helper to partition incoming Telegram updates according to persistent offset bookmark.
    - If offset is None (first run / lost bookmark / silent baseline):
        returns ([], max(update_id)+1) if updates exist, else ([], None).
    - If offset is valid (int):
        returns only updates with id > offset, and new_offset = max(their ids)+1 (or offset if none);
        older/equal ids are ignored.
    - If empty updates list:
        returns ([], offset).
    """
    if not updates:
        return [], offset

    if offset is None:
        valid_ids = [u["update_id"] for u in updates if isinstance(u, dict) and u.get("update_id") is not None]
        if not valid_ids:
            return [], None
        return [], max(valid_ids) + 1

    new_items = [
        u for u in updates
        if isinstance(u, dict) and u.get("update_id") is not None and u["update_id"] > offset
    ]
    if new_items:
        new_offset = max(u["update_id"] for u in new_items) + 1
        return new_items, new_offset
    return [], offset


def poll_once() -> None:
    """
    Check for new Telegram updates, execute any commands, and update offset.
    Follows silent baseline rule: if offset file was missing/empty, establishes
    the baseline without replying, commits tg_offset.txt, and skips the reply phase.
    """
    last_offset = load_tg_offset()

    # SILENT BASELINE RULE
    if last_offset is None:
        print(f"No persistent offset found in {TG_OFFSET_FILE}. Establishing silent baseline...")
        updates = get_updates(offset=None)
        _, new_offset = select_new_updates(updates, None)
        if new_offset is not None:
            save_tg_offset(new_offset)
            print(f"Silent baseline established: offset bookmark set to {new_offset}. Skipping reply phase entirely.")
            git_commit_listener_updates("Establish Telegram silent baseline offset [skip ci]")
        else:
            print("Silent baseline: No pending Telegram updates found.")
        return

    # Valid offset exists -> process new updates
    updates = get_updates(offset=last_offset)
    if not updates:
        return

    # In Telegram, last_offset in tg_offset.txt is already highest_id + 1.
    # Passing (last_offset - 1) as the reference offset to select_new_updates ensures:
    # (1) Any update with id >= last_offset is captured as new.
    # (2) Any older update with id <= last_offset - 1 is safely ignored.
    new_updates, new_offset = select_new_updates(updates, last_offset - 1)

    for update in new_updates:
        message = update.get("message") or update.get("channel_post")
        if not message:
            continue

        text = message.get("text")
        chat = message.get("chat") or {}
        chat_id = chat.get("id")

        if text and chat_id:
            reply = handle_command(text, chat_id)
            if reply:
                send_telegram(reply, kind="reply")

    if new_offset is not None and new_offset != last_offset:
        save_tg_offset(new_offset)
        git_commit_listener_updates("Auto-update Telegram offset and journal [skip ci]")


def poll_loop() -> None:
    """
    Poll Telegram for journal commands.
    If ONESHOT=1 is set, runs poll_once() once and exits immediately (suitable for 5-min cron workflows).
    Otherwise, polls continuously every 5 seconds.
    """
    if os.getenv("ONESHOT", "0").strip() == "1":
        print("Running Telegram listener in ONESHOT mode (processing pending updates once)...")
        poll_once()
        print("ONESHOT update processing completed.")
        return

    print("Telegram journal bot listener started. Polling every 5 seconds... (Press Ctrl+C to stop)")
    while True:
        try:
            poll_once()
        except KeyboardInterrupt:
            print("Telegram listener stopped by user.")
            break
        except Exception as exc:
            print(f"Polling loop exception: {exc}")
        time.sleep(5)


def git_commit_and_push(files: List[str], commit_message: str) -> bool:
    """
    Robust git helper for auto-committing and pushing files to origin main.
    Before pushing, runs 'git pull --rebase origin main'.
    On conflict/failure retries the push once.
    Wrapped in try/except so git errors never crash the run.
    """
    if os.getenv("SKIP_GIT_PUSH", "0").strip() == "1":
        print("SKIP_GIT_PUSH=1: Skipping git commit & push.")
        return True

    try:
        import subprocess

        # Set default git identity if unset (for serverless environments)
        name_check = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True)
        if not name_check.stdout.strip():
            subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
            subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)

        # Stage files that exist
        staged_any = False
        for f in files:
            if os.path.exists(f):
                subprocess.run(["git", "add", f], check=True, capture_output=True, text=True)
                staged_any = True

        if not staged_any:
            return True

        diff_proc = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
        if diff_proc.returncode == 0:
            print(f"No changes in {files} to commit.")
            return True

        commit_proc = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"Git committed: {commit_proc.stdout.strip()}")

        # Pull with rebase before pushing
        pull_proc = subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            capture_output=True,
            text=True,
        )
        if pull_proc.returncode != 0:
            print(f"Warning: git pull --rebase failed: {pull_proc.stderr.strip()}. Aborting rebase if in progress.")
            subprocess.run(["git", "rebase", "--abort"], capture_output=True)

        push_proc = subprocess.run(
            ["git", "push", "origin", "main"],
            capture_output=True,
            text=True,
        )
        if push_proc.returncode == 0:
            print("Git pushed updates to origin main.")
            return True

        # Push failed, retry once with pull --rebase
        print(f"Git push failed ({push_proc.stderr.strip()}), retrying push once...")
        pull_retry = subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            capture_output=True,
            text=True,
        )
        if pull_retry.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], capture_output=True)

        push_retry = subprocess.run(
            ["git", "push", "origin", "main"],
            capture_output=True,
            text=True,
        )
        if push_retry.returncode == 0:
            print("Git pushed updates to origin main on retry.")
            return True
        else:
            print(f"Git push retry failed: {push_retry.stderr.strip()}")
            return False

    except Exception as exc:
        print(f"Git auto-commit failed (non-blocking): {exc}")
        return False


def git_commit_scan_results() -> None:
    """
    Commit and push scan_results.json to origin main.
    Skips if SKIP_GIT_PUSH environment variable is set to '1'.
    Fails safely so git errors never break the scanner.
    """
    git_commit_and_push([SCAN_RESULTS_FILE], "update scan results [skip ci]")


def git_commit_listener_updates(commit_message: str = "Auto-update Telegram offset and journal [skip ci]") -> None:
    """
    Commit and push listener updates (tg_offset.txt, alert_settings.json, trades.json, open_positions.json).
    Skips if SKIP_GIT_PUSH environment variable is set to '1'.
    Fails safely so git errors never break the listener.
    """
    files = [TG_OFFSET_FILE, ALERT_SETTINGS_FILE, TRADES_FILE, OPEN_POSITIONS_FILE]
    git_commit_and_push(files, commit_message)


# =====================================================================
# 11) SCRIPT ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    if "--poll" in sys.argv:
        poll_loop()  # long-running, for the listener workflow
    else:
        settings = load_alert_settings()
        is_digest = settings.get("digest", False)

        # 1. Run daily setup scanner
        signals, scanned_count, is_mkt_ok = run_scanner()

        # 2. Build watchlist candidates & send Telegram alert
        watchlist_candidates = get_watchlist_candidates()
        if SEND_WATCHLIST:
            wl_text = build_watchlist_text(watchlist_candidates)
            if is_digest:
                _DIGEST_MESSAGES.append(("watchlist", wl_text))
            else:
                send_telegram(wl_text, kind="proactive", msg_type="watchlist")

        # 3. Build on-deck & leaders board
        on_deck = get_on_deck_candidates()
        leaders_board = get_leaders_board()

        # 4. Check open positions for upcoming events & warning lines
        open_positions = load_open_positions()
        curr_scan_date = datetime.date.today()
        updated_open_positions, open_event_warn_lines = check_open_positions_events(open_positions, curr_scan_date)
        if updated_open_positions:
            save_open_positions(updated_open_positions)

        # 5. Institutional footprint EOD alert line
        acc_syms = [s["Symbol"] for s in signals if s.get("inst_footprint") == "accumulation"]
        acc_syms += [w["Symbol"] for w in watchlist_candidates if w.get("inst_footprint") == "accumulation" and w["Symbol"] not in acc_syms]
        acc_syms += [o["symbol"] for o in on_deck if o.get("inst_footprint") == "accumulation" and o["symbol"] not in acc_syms]

        inst_tg_line = ""
        if acc_syms:
            eg_syms = ", ".join(acc_syms[:3])
            inst_tg_line = f"🏦 Institutional: {len(acc_syms)} accumulation among signals/on-deck (e.g. {eg_syms})"

        if inst_tg_line:
            if is_digest:
                _DIGEST_MESSAGES.append(("scan", inst_tg_line))
            else:
                send_telegram(inst_tg_line, kind="proactive", msg_type="scan")

        for w_line in open_event_warn_lines:
            if is_digest:
                _DIGEST_MESSAGES.append(("scan", w_line))
            else:
                send_telegram(w_line, kind="proactive", msg_type="scan")

        # In digest mode, combine valid parts into 1 message and send once
        if is_digest and _DIGEST_MESSAGES:
            enable_flags = settings.get("enable", {})
            valid_parts = [
                text for mtype, text in _DIGEST_MESSAGES
                if enable_flags.get(mtype, True) and text.strip()
            ]
            if valid_parts:
                separator = "\n\n" + ("-" * 30) + "\n\n"
                combined_digest = separator.join(valid_parts)
                send_telegram(combined_digest, kind="proactive", msg_type="scan")
            _DIGEST_MESSAGES.clear()

        # 6. Publish scan_results.json for web dashboard
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now_ist = datetime.datetime.now(ist_tz).isoformat()

        total_scanned = scanned_count if scanned_count > 0 else len(get_symbols())
        market_summary = compute_market_summary()

        all_active_symbols = list(dict.fromkeys(
            [s["Symbol"] for s in signals] +
            [w["Symbol"] for w in watchlist_candidates] +
            [o["symbol"] for o in on_deck] +
            [p.get("symbol") for p in open_positions if p.get("symbol")]
        ))
        landmines = get_landmines(all_active_symbols, curr_scan_date)
        deals = load_deals()
        deals_stale = is_deals_stale(deals, curr_scan_date)

        inst_summary = {
            "accumulation_count": sum(1 for x in watchlist_candidates if x.get("inst_footprint") == "accumulation"),
            "churn_count": sum(1 for x in watchlist_candidates if x.get("inst_footprint") == "churn"),
            "unknown_count": sum(1 for x in watchlist_candidates if x.get("inst_footprint") == "unknown"),
            "symbols_accumulating": acc_syms,
        }

        correlation = compute_open_positions_correlation(open_positions)
        sector_rotation = compute_sector_rotation(get_symbols(), on_deck=on_deck)

        scan_results = {
            "updated_at": now_ist,
            "market_ok": is_mkt_ok,
            "signals": signals,
            "watchlist": watchlist_candidates,
            "scanned_count": total_scanned,
            "market_summary": market_summary,
            "on_deck": on_deck,
            "leaders_board": leaders_board,
            "inst_summary": inst_summary,
            "deals_stale": deals_stale,
            "landmines": landmines,
            "correlation": correlation,
            "sector_rotation": sector_rotation,
        }

        with open(SCAN_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(scan_results, f, indent=2, ensure_ascii=False)
        print(f"Published scan results to {SCAN_RESULTS_FILE}")

        # 4. Attempt git auto-commit of scan_results.json
        git_commit_scan_results()

