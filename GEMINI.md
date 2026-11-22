# Security & Confidentiality Rules

## Core Directives
1. **No Hardcoded Secrets or Tokens**:
   - NEVER commit or hardcode `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, GitHub Personal Access Tokens (PAT), or API keys into any source code, tests, documentation, or commit messages.
   - All credentials must be read exclusively from environment variables locally (`.env` which is git-ignored) and from GitHub Actions Secrets (`${{ secrets.TELEGRAM_BOT_TOKEN }}`, `${{ secrets.TELEGRAM_CHAT_ID }}`) in CI/CD.

2. **Public Repository Safety**:
   - Assume this repository may be public. Therefore:
     - Keep `.env` strictly in `.gitignore`.
     - Never expose secrets in log outputs or error messages.
     - Never put sensitive tokens or auth bypass keys in client-side static JavaScript files.

3. **Dashboard Password Protection**:
   - The trading terminal and portfolio dashboard must require login password protection.
   - Never embed actual sensitive passphrases or unhashed secret keys in client-side JavaScript committed to the public repo.
   - Authentication must be validated against environment variables (e.g., Netlify environment variables `DASH_KEY_HASH`).

4. **Trading & State Privacy**:
   - Ensure trade history, open positions, and alert configurations are safeguarded against unauthorized tampering or unintended public exposure.

---

# Architecture & Production Trading Rules

## P0 Core Invariants & Bug Fixes (Audit 2026-11)

### 1. Zero Lookahead Bias in `add_indicators()`
- **Problem**: Previously, `calculate_ofi20(df)`, `calculate_weekly_rs_slope(df)`, and `calculate_vol_adj_return(df)` computed a single scalar from the tail bars of `df` and broadcasted it across every historical row.
- **Fix**: All three indicators are refactored into vectorized, point-in-time rolling Series inside `add_indicators()` so row $t$ strictly uses information available on or before bar $t$ ($\le t$):
  - **Rolling 20-day CMF (`CMF20`)**:
    $$\text{CLV}_t = \text{clip}\left(\frac{(C_t - L_t) - (H_t - C_t)}{H_t - L_t}, -1.0, 1.0\right)$$
    $$\text{CMF20}_t = \frac{\sum_{i=0}^{19} \text{CLV}_{t-i} \cdot V_{t-i}}{\sum_{i=0}^{19} V_{t-i}}$$
    $$\text{OBV\_CONFIRM}_t = (\text{OBV}_t > \text{OBV\_HIGH20}_t) \land (\text{CMF20}_t \ge \text{OFI\_GATE})$$
    (falls back to $\text{OBV}_t > \text{OBV\_HIGH20}_t$ where $\text{CMF20}_t$ is NaN).
  - **Rolling `MOMENTUM_OK`**:
    $$\text{VolAdjRet}_t = \frac{C_t / C_{t-126} - 1}{\text{rolling\_std}_{126}(\Delta\% C)}$$
    $$\text{MOMENTUM\_OK}_t = (\text{VolAdjRet}_t > 0)$$
  - **Rolling Date-Aligned `RS_SLOPE_OK`**: Symbol history and benchmark history (`^CNXSC`) are aligned strictly on `Date` via `pd.merge_asof(..., direction="backward")` before computing the 4-week RS ratio $R_t = C_{\text{sym}, t} / C_{\text{bench}, t}$ and its OLS slope across 4 weekly intervals ($t, t-5, t-10, t-15$).
- Diagnostic callers (`calculate_ofi20`, `calculate_weekly_rs_slope`, `calculate_vol_adj_return`) remain intact for single-value universe ranking and dashboard summaries.

### 2. Corporate Action Adjustment in `get_history()`
- **Problem**: `yf.download(..., auto_adjust=False)` previously left historical bars unadjusted for stock splits, bonus issues, and dividends occurring beyond the last 10 sessions, corrupting historical 50/150/200 SMAs and 52-week highs.
- **Fix**: Configured `yf.download(..., auto_adjust=True)` across the full 2-year history window. `check_corp_action_glitch()` is retained as an active circuit guard against sudden unadjusted feed jumps ($>21\%$ single-session price discontinuity).

### 3. Small-Cap Safe Earnings Blackout & Visibility Toggle
- **Problem**: When `earnings_dates.json` lacked an entry for a symbol, `check_earnings_blackout()` previously failed closed by default and silently rejected 100% of candidate signals.
- **Fix**:
  - Implemented `refresh_earnings_dates(symbols)` to automatically fetch and cache upcoming corporate earnings from `yf.Ticker(sym).calendar` into `earnings_dates.json`.
  - Strict blackout remains enforced whenever a confirmed earnings date falls within `EARNINGS_BLACKOUT_DAYS = 5` sessions to eliminate -20% lower circuit earnings gap risk.
  - Added configuration toggle `EARNINGS_FAIL_CLOSED = False` (configurable via environment variable): when earnings dates are genuinely unavailable after lookup, trade signals are permitted with a prominent warning flag `"earnings_status": "UNVERIFIED — CHECK NSE BEFORE ORDER"` in the Telegram alert and dashboard, ensuring no high-probability setups are silently killed while maintaining full risk transparency.
