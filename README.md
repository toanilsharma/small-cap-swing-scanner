# NIFTY Midcap 100 Swing Trading Scanner

An automated daily swing-trading scanner for the NIFTY Midcap 100 index with real-time Telegram alerts. It identifies high-probability momentum setups combining Mark Minervini's Trend Template, Volatility Contraction Patterns (VCP), Bollinger/Keltner squeezes, and RSI mean-reversion pullbacks, paired with strict risk management and position sizing.

---

## Features

- **Minervini Trend Template**: Filters for stocks in Stage 2 uptrends using alignment across 50, 150, and 200-day Simple Moving Averages (SMAs), 50-day moving average slopes, and 52-week High/Low proximity.
- **VCP & Squeeze Setup**: Detects volume dry-ups (`VOL5 < 0.8 * VOL50`) and price volatility contractions (`RANGE5 < 0.8 * RANGE50`), as well as Bollinger Bands coiling inside Keltner Channels (`SQUEEZE_ON`).
- **Breakout & Pullback Triggers**:
  - **Breakout**: Fresh cross above the 20-day high (excluding today) accompanied by volume spikes (>1.5x 50-day average) and strong candle closes in the upper 40% of the daily range.
  - **Pullback**: 2-period RSI oversold reversal (`RSI2 < 10` crossing up from previous day) with positive price confirmation.
- **Market Direction Filter**: Implements William O'Neil's M-rule on the benchmark index (`^NSEI`). Scanner entries are blocked unless the index is in a confirmed uptrend (Close > SMA50 > SMA200).
- **Liquidity & Relative Strength**:
  - Requires a minimum 50-day average daily turnover of ₹20 Crores to ensure seamless execution.
  - Requires stock 50-day percentage performance to outperform the benchmark index.
- **ATR Stop Loss & 1% Risk Sizing**:
  - Stop loss anchored dynamically to 1.5x ATR(14) with a hard floor capped at 7% maximum risk.
  - Profit target calculated at 2R (2:1 reward-to-risk ratio).
  - Exact share quantities calculated from a fixed 1% account equity risk (`CAPITAL * RISK_PCT / risk_per_unit`).
- **Watchlist Generator**: Identifies uptrending stocks coiling within 5% of their 20-day breakout level, sorted by distance.

---

## Local Setup

### 1. Prerequisites

- Python 3.10+ installed on your system.

### 2. Install Dependencies

Clone or navigate to the workspace directory and install the required Python packages:

```bash
pip install -r requirements.txt
```

### 3. Environment Configuration

Copy the sample environment file to `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in your Telegram credentials:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

_(Never commit `.env` to version control; it is ignored in `.gitignore`.)_

### 4. Custom Symbols (Optional)

By default, if `symbols.txt` is empty or absent, the scanner automatically downloads the constituent list of the NIFTY Midcap 100 directly from NSE/NiftyIndices.

If you wish to scan a custom basket of symbols instead, list them in `symbols.txt` (one per line, with or without `.NS`):

```text
PERSISTENT
DIXON
COFORGE
```

---

## How to Run

Run the scanner locally after market close (recommended between 15:45 and 16:30 IST):

```bash
python main.py
```

The script will:

1. Verify the benchmark index market regime.
2. Scan all candidate symbols and compute indicators.
3. Transmit all detected breakout and pullback setups to your Telegram chat with entry, stop loss, target, position quantity, and risk discipline rules.
4. Deliver a watchlist summary of stocks nearing breakouts.

---

## Automation (GitHub Actions)

This repository includes an automated workflow configured in `.github/workflows/daily_scan.yml`:

- **Schedule**: Runs automatically Monday through Friday at **16:15 IST** (10:45 UTC).
- **Manual Trigger**: Can be dispatched manually anytime from the GitHub Actions tab.
- **Secrets Setup**: Add your credentials as GitHub Repository Secrets under **Settings > Secrets and variables > Actions**:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`

---

## Sector Filter (Double Confirmation Rule)

To prevent buying stocks swimming against their industry current, the scanner applies a **double-confirmation sector filter**:

1. **Benchmark Filter**: The broader market index (`^NSEI`) must satisfy `Close > SMA50 > SMA200`.
2. **Sector Index Filter**: Each individual stock's sector index must also be in an active Stage 2 uptrend (`Close_sector > SMA50_sector > SMA200_sector`).
3. **Live Verified Sector Indices**:
   - **IT**: `^CNXIT`
   - **Banking & Financials**: `^NSEBANK`
   - **Auto**: `^CNXAUTO`
   - **Pharma & Healthcare**: `^CNXPHARMA`
   - **FMCG**: `^CNXFMCG`
   - **Metal**: `^CNXMETAL`
   - **Realty**: `^CNXREALTY`
   - **Media**: `^CNXMEDIA`
   - **PSU Bank**: `^CNXPSUBANK`
   - **Infra & Capital Goods**: `^CNXINFRA`
   - _Stocks in sectors with unlisted or erratic Yahoo indices default gracefully to `^NSEI`._
4. **Fail-Open Safety**: If any sector index feed is unavailable or missing data, the filter fails open (`True`) so technical glitches never obstruct valid trades.

---

## Trade Journal Commands (Telegram P&L Tracker)

You can manage your entire trading journal in real time directly through Telegram messages to your bot.

### Available Commands

| Command       | Syntax                                  | Description & Example                                                                          |
| ------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **`/buy`**    | `/buy SYMBOL ENTRY QTY [STOP] [TARGET]` | Log a new position to `open_positions.json`<br>`/buy DIXON 12500 8 11800 13900`                |
| **`/sell`**   | `/sell SYMBOL EXIT [NOTE]`              | Close active trade, log PnL & R-multiple to `trades.json`<br>`/sell DIXON 13900 Hit 2R target` |
| **`/open`**   | `/open`                                 | View all active positions with entry date, price, qty, stop, and target                        |
| **`/trades`** | `/trades`                               | List your last 10 closed trades with realized PnL and return %                                 |
| **`/stats`**  | `/stats`                                | View performance metrics: Win Rate, Profit Factor, Expectancy, Max Drawdown & PnL              |
| **`/help`**   | `/help`                                 | Display the interactive command menu and syntax hints                                          |

### Running the Telegram Listener

- **Continuous Polling (Local)**:

  ```bash
  python main.py --poll
  ```

  Polls every 5 seconds for new commands. Press `Ctrl+C` to stop.

- **Serverless 5-Minute Automation (GitHub Actions)**:
  Configured in `.github/workflows/telegram_listener.yml`:
  Runs every 5 minutes in `ONESHOT=1` mode, processes pending user commands, updates `trades.json` and `open_positions.json`, and commits updates back to GitHub.

---

## Logic Audit (do not skip)

To safeguard trading integrity and prevent unintended changes to indicator definitions, signal generation, risk budgeting, or notification gating, this repository includes an offline regression harness.

### How to Run

Install development dependencies and run the audit:

```bash
pip install -r tests/requirements-dev.txt
python audit.py
```

Expected output:

```text
============================================================
AUDIT SCOREBOARD
============================================================
RULES GOLDEN ............. PASS
RISK MATH ................ PASS
NOTIFY GATING ............ PASS
OFFSET STATE ............. PASS
HERMETIC SCAN ............ PASS
SCHEMA DRIFT ............. PASS
============================================================
All trading-logic invariants intact.
============================================================
```

### What Each Layer Protects

1. **RULES GOLDEN (`tests/test_rules_golden.py`)**: Pins the exact 12-indicator AND-logic vector across 4 synthetic scenarios (Textbook Long, Downtrend, Breakout without Volume, and Coiling without Breakout). Compares against `tests/GOLDEN_RULES.json`.
2. **RISK MATH (`tests/test_risk_math.py`)**: Pins ATR-based stop sizing (1.5x ATR), the 7% stop loss floor cap, 2R profit targets, and fixed 1% equity position sizing calculations.
3. **NOTIFY GATING (`tests/test_notification_gating.py`)**: Verifies that Telegram alerts respect `QUIET=1`, quiet hour windows (21:00-08:00 IST), and category flags, while proving that muting notifications **never blocks data collection or `scan_results.json` generation**.
4. **OFFSET STATE (`tests/test_offset_state.py`)**: Guarantees the Telegram listener state machine establishes a silent baseline on new/lost offsets and ignores stale or duplicate messages to prevent night spam.
5. **HERMETIC SCAN (`tests/test_hermetic_scan.py`)**: End-to-end integration test validating that scanning, watchlist ranking, and digest bundling operate seamlessly 100% offline.
6. **SCHEMA DRIFT (`tests/test_schema_drift.py`)**: Locks the JSON schema and key names in `scan_results.json` so the Netlify frontend dashboard never encounters missing or renamed properties.

### Regenerating Golden Rules Snapshot

If (and only if) an intentional, reviewed change is made to trading rules:

```bash
python audit.py --regen-golden
```

This overwrites `tests/GOLDEN_RULES.json` with the new rule vectors.

### THE RULE

> [!IMPORTANT]
> **Any future change request to this repo must end with:**
> Run `python audit.py`. If any test fails, fix the cause before pushing — **never regenerate the golden unless the rule change was intentional and reviewed.**

---

## Risk Disclaimer

> [!WARNING]
> This software is developed purely for **educational and research purposes**. It does not constitute financial, investment, or trading advice. Swing trading and stock market participation carry substantial risk of capital loss. Always perform your own due diligence, review company earnings dates, and consult a certified financial advisor before executing trades with real money.
