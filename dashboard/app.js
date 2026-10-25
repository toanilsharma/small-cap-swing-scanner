const OWNER = "toanilsharma";
const REPO  = "small-cap-swing-scanner";
const REPO_OWNER = OWNER;
const REPO_SLUG  = REPO;

// =====================================================================
// DATA ENDPOINTS (Direct public GitHub raw URLs, anonymous, zero secrets)
// =====================================================================
const RAW_BASE_URL = `https://raw.githubusercontent.com/${OWNER}/${REPO}/main`;
const SCAN_RESULTS_URL = `${RAW_BASE_URL}/scan_results.json`;
const OPEN_POSITIONS_URL = `${RAW_BASE_URL}/open_positions.json`;
const TRADES_URL = `${RAW_BASE_URL}/trades.json`;
const BACKTEST_RESULTS_URL = `${RAW_BASE_URL}/backtest_results.json`;

let equityChartInstance = null;
let backtestChartInstance = null;
let _liveScanData = null;
let _cachedTradesData = null;
let _cachedBacktestData = null;
let _isViewingArchive = false;

// =====================================================================
// SITE-WIDE TERMS & DEFINITIONS DICTIONARY
// =====================================================================
const TERMS = {
  // Moving Averages & Trend
  "SMA50": {
    short: "50-day Simple Moving Average representing 10 weeks of institutional price trend.",
    long: "The 50-day Simple Moving Average calculates the mean closing price over the last 10 calendar weeks. In Minervini Stage 2 uptrends, leading stocks stay above their rising SMA 50, which serves as primary institutional support.",
    where_used: "Near Buy (Trend Filter), Help Guide",
    anchor: "glossary-sma50"
  },
  "SMA150": {
    short: "150-day Simple Moving Average tracking intermediate-term institutional support.",
    long: "The 150-day Simple Moving Average reflects roughly 7 months of price action. It validates healthy intermediate trend structure by staying positioned between the 50 SMA and 200 SMA in Stage 2 leaders.",
    where_used: "Near Buy (Trend Filter), Help Guide",
    anchor: "glossary-sma150"
  },
  "SMA200": {
    short: "200-day Simple Moving Average defining the macro boundary between bull and bear trends.",
    long: "The premier long-term benchmark average representing ~10 months of trading. Minervini rules require the 200 SMA to be trending up for at least 1 month before taking any long swing trades.",
    where_used: "Near Buy (Trend Filter), Help Guide",
    anchor: "glossary-sma200"
  },
  "EMA10": {
    short: "10-period Exponential Moving Average used as our mechanical trailing stop line.",
    long: "A fast moving average heavily weighted toward recent prices. Once a winning swing trade surpasses its initial 2R target, we trail our stop loss along the daily 10 EMA to ride multi-week momentum runners.",
    where_used: "Open Positions, Trade Management, Help Guide",
    anchor: "glossary-ema10"
  },
  "EMA20": {
    short: "20-period Exponential Moving Average capturing short-term pullbacks and base support.",
    long: "The 20-period Exponential Moving Average approximates a 1-month trading trend. Strong momentum stocks routinely test and bounce off their rising 20 EMA while forming volatility squeezes.",
    where_used: "Indicators, Mini Charts, Help Guide",
    anchor: "glossary-ema20"
  },
  "ATR14": {
    short: "14-day Average True Range measuring true daily volatility in rupees.",
    long: "ATR measures the average rupee swing per session, accounting for overnight gap moves. It allows us to set dynamic, volatility-based stop losses rather than using arbitrary percentage stops.",
    where_used: "Position Sizer, Watchlist, Help Guide",
    anchor: "glossary-atr14"
  },
  "RSI14": {
    short: "Standard 14-day Relative Strength Index oscillator filtering momentum extremes.",
    long: "Bounded between 0 and 100, RSI14 measures the magnitude of recent gains versus losses. Our scanner rewards candidates with RSI14 between 40 and 65, ensuring positive momentum without chasing overbought tops.",
    where_used: "Near Buy (Score Filter), Help Guide",
    anchor: "glossary-rsi14"
  },
  "RSI2": {
    short: "Ultra-fast 2-period RSI oscillator designed to spot short-term rubber-band dips.",
    long: "Popularized by Larry Connors, 2-period RSI drops into extreme oversold territory (<10) during quick 2-3 day pullbacks. Buying the subsequent green reversal candle offers exceptional reward-to-risk asymmetry.",
    where_used: "Pullback Setup, Help Guide",
    anchor: "glossary-rsi2"
  },
  "Volume": {
    short: "Total number of shares transacted during a trading day.",
    long: "Volume confirms the validity of price movements. Without volume, price breakouts lack genuine institutional sponsorship and frequently fail due to low liquidity.",
    where_used: "Turnover Filter, Volume Dry-up, Help Guide",
    anchor: "glossary-volume"
  },
  "Volume dry-up": {
    short: "Trading activity shrinking below 80% of normal, proving sellers are exhausted.",
    long: "When 5-day average volume drops below 80% of the 50-day average, supply has completely dried up. With few shares left for sale, it takes minimal buyer interest to trigger an explosive breakout.",
    where_used: "Near Buy (Coiling Setup), Help Guide",
    anchor: "glossary-volumedryup"
  },
  "50-day average volume": {
    short: "The 50-session moving average of volume acting as our liquidity baseline.",
    long: "Calculates baseline turnover and participation. Serves as the quantitative yardstick against which both volume dry-ups (<80%) and breakout volume spikes (>150%) are measured.",
    where_used: "Near Buy Filter, Help Guide",
    anchor: "glossary-vol50"
  },
  "VCP / coiling": {
    short: "Volatility Contraction Pattern showing shrinking price swings and dried-up volume.",
    long: "Mark Minervini's signature institutional pattern where each successive pullback becomes shallower (e.g. -15% then -8% then -3%). When accompanied by volume dry-up, it indicates institutional absorption.",
    where_used: "Near Buy (Coiling Badge), Help Guide",
    anchor: "glossary-vcp"
  },
  "Coiling": {
    short: "A tight consolidation where price range and volume both contract significantly.",
    long: "Indicates that buyers and sellers have reached price equilibrium under resistance. A 'Coiling: YES' tag confirms the stock is spring-loaded and eligible for immediate breakout triggers.",
    where_used: "Near Buy Table Header & Badges, Help Guide",
    anchor: "glossary-vcp"
  },
  "price contraction": {
    short: "Daily candle trading range narrowing below 80% of historical average range.",
    long: "Measured as 5-day average high-low range dropping below 80% of the 50-day range. Confirms volatility compression before a rapid expansion in price.",
    where_used: "Near Buy (VCP Setup), Help Guide",
    anchor: "glossary-pricecontraction"
  },
  "20-day breakout level": {
    short: "The highest intra-day price reached across the previous 20 trading sessions.",
    long: "Represents the overhead resistance level that trapped prior buyers. Penetrating this level on high volume signals that all overhead sellers are cleared.",
    where_used: "Near Buy Table, Mini Charts, Help Guide",
    anchor: "glossary-high20"
  },
  "breakout": {
    short: "Price crossing and closing above a critical resistance ceiling on heavy volume.",
    long: "A valid breakout occurs when a coiled Stage 2 stock closes above its 20-day high on volume >1.5x average. It triggers our automated /buy signal on Telegram.",
    where_used: "Signals Table, Telegram Alerts, Help Guide",
    anchor: "glossary-breakout"
  },
  "volume spike": {
    short: "Daily volume exceeding 1.5 times the 50-day average volume.",
    long: "The indispensable fuel behind every genuine breakout. Institutional funds cannot enter or accumulate a stock quietly on a breakout without creating an obvious volume spike.",
    where_used: "Breakout Confirmation, Help Guide",
    anchor: "glossary-volumespike"
  },
  "strong close": {
    short: "Session candle finishing in the top 40% of its daily high-to-low range.",
    long: "Calculated as (Close - Low) / (High - Low) > 0.60. Filters out intraday upper rejection wicks and proves that buyers retained aggressive control into the closing bell.",
    where_used: "Signal Confirmation, Help Guide",
    anchor: "glossary-strongclose"
  },
  "52-week high and low": {
    short: "The annual peak and trough prices defining the stock's 1-year trading boundary.",
    long: "Minervini Stage 2 criteria require price to trade at least 30% above its 52-week low and within 25% of its 52-week high. Winning swing trades emerge near 52-week highs, not lows.",
    where_used: "Trend Filter, Help Guide",
    anchor: "glossary-52whighlow"
  },
  "Relative Strength vs index": {
    short: "Outperformance of an individual stock compared to the NIFTY 50 benchmark.",
    long: "Stocks with high Relative Strength resist market sell-offs and reach new highs first. Our strategy focuses strictly on market leaders with sector and index outperformance.",
    where_used: "Trend Ranking, Help Guide",
    anchor: "glossary-rs"
  },
  "Sector filter": {
    short: "Requirement that the stock's industry sector index is also in an active Stage 2 uptrend.",
    long: "Verifies that the stock's broader industry index (e.g. NIFTY IT, NIFTY Bank) is trading above its 50 and 200 SMAs. Prevents buying isolated winners in declining sector groups.",
    where_used: "Near Buy (Sector Bullish), Help Guide",
    anchor: "glossary-sectorfilter"
  },
  "Sector Bullish": {
    short: "Confirmation that the stock's sector index is in an active Stage 2 uptrend.",
    long: "Displays 'YES' if the company's sector index satisfies Close > SMA50 > SMA200. Adds +15 points to the Setup Score and is required for Grade A and A+ status.",
    where_used: "Near Buy Table Column & Badges, Help Guide",
    anchor: "glossary-sectorfilter"
  },
  "Market regime (M-rule)": {
    short: "O'Neil benchmark index filter based on NIFTY 50 moving averages.",
    long: "75% of individual stocks follow the broader market trend. If the NIFTY 50 index falls below its 50 or 200 SMA, the market flips to Defensive, capping all scores at 50 and blocking buy signals.",
    where_used: "Top Bar Market Badge, Regime Banner, Help Guide",
    anchor: "glossary-mrule"
  },
  "Market regime": {
    short: "Macro market environment filter: Uptrend (trading permitted) vs Defensive (cash only).",
    long: "Evaluates whether NIFTY 50 is trading cleanly above its 50-day and 200-day moving averages. If market conditions deteriorate, capital preservation mandates holding cash.",
    where_used: "Top Bar Header, Near Buy Tab, Help Guide",
    anchor: "glossary-mrule"
  },
  "Defensive": {
    short: "Market regime indicating benchmark downtrend; cash is held to protect capital.",
    long: "When NIFTY 50 breaks below key moving averages, the terminal badge displays 'Market: Defensive'. All setup scores are capped at 50 and no new purchases are allowed.",
    where_used: "Market Badge, Regime Banner, FAQ, Help Guide",
    anchor: "glossary-mrule"
  },
  "Distance to breakout": {
    short: "Percentage distance from current closing price to the 20-day high resistance level.",
    long: "Stocks within 0-2% of breakout receive top priority for immediate entry. Stocks between 2% and 5% are kept on the watchlist for observation.",
    where_used: "Near Buy Table, Score Calculation, Help Guide",
    anchor: "glossary-dist"
  },
  "Dist to Breakout": {
    short: "Percentage distance remaining before the stock reaches its 20-day breakout trigger.",
    long: "Quantifies how close the setup is to breaking out. Scaled into the Setup Score (up to +20 points for candidates within 2% of the breakout line).",
    where_used: "Near Buy Table Header, Help Guide",
    anchor: "glossary-dist"
  },
  "Setup window": {
    short: "10-day lookback buffer during which a prior coiling pattern remains valid.",
    long: "Breakouts do not always trigger on the exact session a stock finishes coiling. A 10-day memory window ensures eligible setups are rewarded when the volume spike arrives.",
    where_used: "Scanner Engine, Help Guide",
    anchor: "glossary-setupwindow"
  },
  "Stop loss": {
    short: "Predefined price level where a trade is automatically liquidated to prevent major losses.",
    long: "Calculated dynamically as Entry minus 1.5x ATR, capped at a maximum of 7% from entry. Strictly executed without hesitation or emotional debate.",
    where_used: "Position Sizer, Open Positions, Help Guide",
    anchor: "glossary-stoploss"
  },
  "1.5x ATR stop": {
    short: "Dynamic stop loss buffer set at 1.5 times the 14-day Average True Range below entry.",
    long: "Adapts stop loss distance to the specific volatility of the stock, preventing normal intraday noise from triggering premature exits.",
    where_used: "Signal Generation, Position Sizer, Help Guide",
    anchor: "glossary-15atr"
  },
  "7% max stop": {
    short: "Absolute hard ceiling capping initial stop loss distance at 7% from entry price.",
    long: "Even if ATR volatility would dictate a wider buffer, the system clamps the stop loss at 7% below entry to maintain favorable expectancy and prevent outsized losses.",
    where_used: "Signal Generation, Position Sizer, Help Guide",
    anchor: "glossary-maxstop"
  },
  "Target": {
    short: "Pre-planned exit price where profits are locked in at a 2:1 reward-to-risk ratio.",
    long: "Set at Entry + 2 * (Entry - Stop). Exiting at predefined 2R targets ensures consistent profitability even when win rate hovers around 45-50%.",
    where_used: "Position Sizer, Open Positions, Help Guide",
    anchor: "glossary-target"
  },
  "2R": {
    short: "Profit target delivering exactly twice the rupee risk taken on the trade.",
    long: "A 2R target produces asymmetric returns: risking ₹1,000 to make ₹2,000. This mathematical asymmetry is the bedrock of profitable swing trading.",
    where_used: "Position Sizer, Open Positions, Help Guide",
    anchor: "glossary-2rtarget"
  },
  "R-multiple": {
    short: "Trade outcome expressed as a multiple of initial risk (1R = Risk Budget).",
    long: "Normalizes performance across different stocks and account sizes. A win of +₹2,000 on a ₹1,000 risk trade is scored as +2.0R, while a stop loss is -1.0R.",
    where_used: "Trade History Table, Help Guide",
    anchor: "glossary-rmultiple"
  },
  "Position size": {
    short: "Exact number of shares to buy so potential loss equals your 1% risk budget.",
    long: "Calculated as floor((Capital * Risk%) / (Entry - Stop)). Sizing according to risk distance rather than capital allocation protects you from oversized losses on volatile stocks.",
    where_used: "Position Sizer, Signals Table, Help Guide",
    anchor: "glossary-positionsize"
  },
  "1% risk rule": {
    short: "Risking no more than 1% of total portfolio capital on any single swing trade.",
    long: "On a ₹100,000 capital account, max loss per trade is strictly capped at ₹1,000. Ensures survival across normal losing streaks without inflicting severe psychological damage.",
    where_used: "Position Sizer, Risk Commandments, Help Guide",
    anchor: "glossary-1percentsizing"
  },
  "Expectancy": {
    short: "Expected average rupee payoff per trade over a large series of trades.",
    long: "Formula: (Win% * AvgWin) - (Loss% * AvgLoss). A positive expectancy (e.g. >₹500 per trade) proves that your trading edge is mathematically sound and profitable.",
    where_used: "Performance Stats Tab, Help Guide",
    anchor: "glossary-expectancy"
  },
  "Win rate": {
    short: "The percentage of closed trades that resulted in a positive realized profit.",
    long: "Calculated as Winning Trades / Total Trades. Because our 2R target delivers twice what our stop loses, a 45-50% win rate generates steady capital growth.",
    where_used: "Performance Stats Tab, Help Guide",
    anchor: "glossary-winrate"
  },
  "Profit factor": {
    short: "Ratio of gross winning rupees divided by gross losing rupees across closed trades.",
    long: "A key health metric of any trading system. A profit factor above 1.5 indicates a robust, reliable edge, while values above 2.0 represent exceptional efficiency.",
    where_used: "Performance Stats Tab, Help Guide",
    anchor: "glossary-profitfactor"
  },
  "Max drawdown": {
    short: "The largest peak-to-trough decline in total portfolio capital.",
    long: "Quantifies the worst drawdown period experienced by the account. Strict adherence to 1% risk and 2% daily loss rules keeps drawdowns well under 8%.",
    where_used: "Performance Stats Tab, Help Guide",
    anchor: "glossary-maxdrawdown"
  },
  "Time stop": {
    short: "Mechanical discipline rule to close a stagnant breakout after 8 trading days without profit.",
    long: "Genuine small-cap momentum breakouts follow through swiftly. If an open position fails to achieve positive momentum and is not in profit after 8 trading sessions (TIME_STOP_DAYS=8), the trade is mechanically liquidated at market close to free up cash for active leaders.",
    where_used: "Trader's Playbook, Risk Commandments, Help Guide",
    anchor: "glossary-timestop"
  },
  "Time Stop": {
    short: "Mechanical discipline rule to close a stagnant breakout after 8 trading days without profit.",
    long: "Genuine small-cap momentum breakouts follow through swiftly. If an open position fails to achieve positive momentum and is not in profit after 8 trading sessions (TIME_STOP_DAYS=8), the trade is mechanically liquidated at market close to free up cash for active leaders.",
    where_used: "Trader's Playbook, Risk Commandments, Help Guide",
    anchor: "glossary-timestop"
  },
  "GTT": {
    short: "Good-Till-Triggered conditional order resting at broker until breakout price triggers execution.",
    long: "A conditional pending order (supported by Zerodha Kite, Groww, etc.) that stays active until triggered or cancelled. For small-cap swing trading breakouts, place a Buy GTT with Trigger = Breakout Price and Limit = Trigger + 0.5% with validity GTC/7d. Avoids emotional execution and never uses market orders.",
    where_used: "Trader's Playbook, Watchlist GTT Generator, Help Guide",
    anchor: "glossary-gtt"
  },
  "Bracket Order": {
    short: "Multi-leg conditional order linking limit entry with automated stop-loss and profit target.",
    long: "A risk-mitigation order type where placing an entry automatically arms both a predefined stop-loss order and a target exit order. If either exit leg fills, the other leg is automatically cancelled (OCO - One Cancels Other).",
    where_used: "Trader's Playbook, Position Sizer, Help Guide",
    anchor: "glossary-bracketorder"
  },
  "Breakeven SL": {
    short: "Adjusting stop loss to exact entry price once trade reaches +2R or partial targets.",
    long: "A crucial capital-protection rule. Once the stock hits its initial +2R profit target and 50% of the position is locked in, the stop loss on the remaining 50% trailing runner is immediately moved up to breakeven (entry price + brokerage buffer). Eliminates downside risk completely.",
    where_used: "Trader's Playbook, Open Positions, Help Guide",
    anchor: "glossary-breakeven"
  },
  "Breakeven ratchet": {
    short: "Moving stop loss up to entry price once trade reaches +8% unrealized profit.",
    long: "Eliminates downside risk by locking in a free trade once price rallies +8%. Guarantees that a substantial winning trade never turns into a losing trade.",
    where_used: "Trade Management, Help Guide",
    anchor: "glossary-breakeven"
  },
  "Breakeven": {
    short: "Adjusting your stop loss to the exact entry price to guarantee zero loss.",
    long: "Triggered mechanically at +8% gain. Once at breakeven, you hold the position risk-free while letting profits run toward the 2R target or 10 EMA trailing exit.",
    where_used: "Trade Management, Help Guide",
    anchor: "glossary-breakeven"
  },
  "Trailing stop (10 EMA)": {
    short: "Dynamic exit technique riding big winners until a session closes below the 10 EMA.",
    long: "Once a stock exceeds its initial 2R target, we hold until a daily candle closes below the rising 10 EMA line. This allows exceptional trends to turn into 3R+ mega winners.",
    where_used: "Trade Management, Help Guide",
    anchor: "glossary-trailingema10"
  },
  "Grade": {
    short: "Setup quality rating (A+, A, B, C) based on score and sector/market confirmation.",
    long: "Grade A+ (Score ≥80 with Bullish Sector & Market OK) and Grade A (Score ≥70 with Bullish Sector) represent top-tier setups. Grade B and C are for observation only.",
    where_used: "Near Buy Table, Signals Table, Help Guide",
    anchor: "glossary-gradescore"
  },
  "Setup score": {
    short: "Composite setup rating from 0 to 100 evaluating trend, coiling, volume, and sector.",
    long: "Combines 7 quantitative factors: Trend (+25), Breakout Proximity (+20), Coiling (+15), Sector (+15), Volume Dry-up (+10), RSI in range (+10), and Market filter (+5).",
    where_used: "Near Buy Table, Help Guide",
    anchor: "glossary-gradescore"
  },
  "Score": {
    short: "Composite setup score (0-100) ranking the statistical edge of each candidate.",
    long: "Scores 80+ indicate Grade A+ setups; scores 70-79 indicate Grade A setups. Directs attention and capital exclusively to the highest probability opportunities.",
    where_used: "Near Buy Table Column & Pills, Help Guide",
    anchor: "glossary-gradescore"
  },
  "Watchlist": {
    short: "Candidate stocks meeting Minervini Stage 2 criteria and within 5% of 20-day high.",
    long: "Refreshed after every market close. Provides early visibility into coiling stocks that are preparing to break out, allowing you to prepare order sizing in advance.",
    where_used: "Near Buy Tab, Help Guide",
    anchor: "glossary-dist"
  },
  "Open positions": {
    short: "Live swing trades currently active in the portfolio with active stops and targets.",
    long: "Monitored against daily market closes. Each position displays real-time paper PnL, percentage distance to protective stop loss, and percentage distance to 2R target.",
    where_used: "Open Positions Tab, Telegram /open, Help Guide",
    anchor: "glossary-positionsize"
  },
  "Unrealized PnL": {
    short: "Floating paper profit or loss on active open positions based on current prices.",
    long: "Reflects mark-to-market performance of active trades. Becomes Realized PnL only after closing the position with a /sell command.",
    where_used: "Open Positions Table & Summary Strip",
    anchor: "glossary-positionsize"
  },
  "Realized PnL": {
    short: "Net rupee profit or loss booked upon closing a position.",
    long: "Recorded in trades.json upon executing /sell. Forms the data points for the cumulative equity curve, win rate, and profit factor calculations.",
    where_used: "Trade History Table, Stats Tab, Help Guide",
    anchor: "glossary-expectancy"
  },
  "% to Stop": {
    short: "Percentage distance from the current price down to your protective stop loss.",
    long: "Highlights how close a position is to triggering its exit stop. Low values (<1.5%) indicate positions requiring defensive attention.",
    where_used: "Open Positions Table Column"
  },
  "% to Target": {
    short: "Percentage distance remaining from current price up to your 2R profit target.",
    long: "Shows progress toward your predefined exit target. As price approaches target, prepare to exit or activate the 10 EMA trailing stop.",
    where_used: "Open Positions Table Column"
  },
  "Equity curve": {
    short: "Cumulative line chart tracking total realized profits and losses over time.",
    long: "Visualizes the trajectory of your trading account. A rising equity curve with shallow pullbacks demonstrates a consistent statistical edge and sound risk management.",
    where_used: "Trade History Tab, Help Guide"
  },
  "Stop moved": {
    short: "Discipline mistake where exit price is worse than planned stop loss.",
    long: "Occurs when a trader cancels, lowers, or fails to honor their initial stop loss, taking a larger loss than planned. Automatic flag: mistake = 'stop_moved'.",
    where_used: "Trade History Table, Stats Tab (Mistakes Tracker), Help Guide"
  },
  "Time stop ignored": {
    short: "Discipline mistake where a sluggish trade is held >5 days with return <3%.",
    long: "Occurs when a trade fails to follow through within 5 days and is not exited, locking up valuable trading capital. Automatic flag: mistake = 'time_stop_ignored'.",
    where_used: "Trade History Table, Stats Tab (Mistakes Tracker), Help Guide"
  },
  "Plan discipline": {
    short: "Tracking win rate and performance of trades executed strictly according to plan.",
    long: "Compares trades tagged #plan_followed against untagged/deviated trades to quantify the performance boost of strict adherence to rules.",
    where_used: "Performance Stats Tab, Help Guide"
  },
  "Trade tags": {
    short: "Hashtags (#breakout, #pullback, #plan_followed, #fomo) categorizing trade execution.",
    long: "Attached to /buy and /sell commands to track edge by setup type and diagnose psychological trading habits.",
    where_used: "Trade History Table, Stats Tab, Telegram Commands"
  },
  "Market Pulse": {
    short: "Responsive real-time macro telemetry bar tracking index price, session close, live IST market hours, and universe breadth.",
    long: "Replaces static loading text with live macro telemetry including NIFTY benchmark change, last EOD bar date, IST market operational hours status, and percentage of small-cap universe trading above 50 and 200 SMAs.",
    where_used: "Top Header Bar, Help Guide",
    anchor: "glossary-marketpulse"
  },
  "Market Summary": {
    short: "Comprehensive diagnostic summary of index price action and market-wide participation metrics.",
    long: "Provides institutional market context computed from daily index bars and small-cap constituent moving averages, including advancer/decliner count and moving average breadth.",
    where_used: "Top Header Bar, Help Guide",
    anchor: "glossary-marketpulse"
  },
  "Market Breadth": {
    short: "Percentage of universe stocks trading above their 50-day and 200-day SMAs alongside advancers vs decliners.",
    long: "Internal market participation indicator. High breadth (>70% above 50 SMA) signals widespread institutional buying support, while declining breadth warns of index divergence and distribution.",
    where_used: "Market Pulse Row, Help Guide",
    anchor: "glossary-breadth"
  },
  "Leaders Board": {
    short: "Top 10 highest Relative Strength (RS 1-99) stocks that are also confirmed in Stage-2 uptrends.",
    long: "Showcases institutional market leaders with the highest composite price momentum over 3, 6, 9, and 12 months that remain in Stage-2 uptrends (Close > SMA50 > SMA150 > SMA200).",
    where_used: "Near Buy (Top Strip), Help Guide",
    anchor: "glossary-leadersboard"
  },
  "On Deck": {
    short: "Stage-2 setups passing Trend and Squeeze filters, within 5% of resistance, awaiting breakout or volume spike.",
    long: "Diagnostic watchlist of near-miss setups positioned under resistance. They satisfy all Stage-2 trend and contraction criteria but have not yet fired a breakout close or 1.5x volume surge.",
    where_used: "Near Buy (Below Watchlist), Help Guide",
    anchor: "glossary-ondeck"
  },
  "Near Misses": {
    short: "Synonym for On Deck candidates positioned under resistance awaiting volume or breakout confirmation.",
    long: "High-quality Stage-2 candidates that fulfill Minervini trend and VCP filters but are waiting for either a price breakout or volume expansion to trigger an official buy signal.",
    where_used: "Near Buy Tab, Help Guide",
    anchor: "glossary-ondeck"
  },
  "RS Rating": {
    short: "IBD-style 1 to 99 percentile score measuring price performance versus the entire market universe.",
    long: "Ranks each stock's weighted return (40% 3M + 20% 6M + 20% 9M + 20% 12M) on a 1-99 percentile scale. Stocks rated RS 90+ are elite leaders; RS 80-89 are strong contenders.",
    where_used: "Watchlist Table (RS Pill), Leaders Board, Help Guide",
    anchor: "glossary-rsrating"
  },
  "Relative Strength": {
    short: "Percentile ranking (1-99) of a stock's 1-year weighted performance compared to all other stocks.",
    long: "Quantifies how strongly a stock is outperforming its peers. A rating of 95 means the stock has outperformed 95% of the universe over the past four quarters.",
    where_used: "Watchlist (RS Pill), Leaders Board, Help Guide",
    anchor: "glossary-rsrating"
  },
  "Base Maturity": {
    short: "Stages of consolidation base development: Fresh (15-35 days), Mature (36-65 days), or Extended (>65 days).",
    long: "Classifies how long a stock has been consolidating. Fresh and mature bases have the highest probability of sustained breakout follow-through; extended bases carry higher risk of late-stage failure.",
    where_used: "Setup Details, Help Guide",
    anchor: "glossary-basematurity"
  },
  "Days in Base": {
    short: "Count of consecutive trading sessions the stock has spent consolidating within a 15% price band.",
    long: "Measures the duration of the current contraction pattern. Institutional accumulation requires sufficient time (typically 3-10 weeks) to absorb overhead supply before initiating a markup.",
    where_used: "Setup Details, Help Guide",
    anchor: "glossary-daysinbase"
  },
  "Institutional Footprint": {
    short: "Tracks big-money behavior: Accumulation (rising delivery % / prints), Churn (high vol, low delivery), or Unknown.",
    long: "Monitors daily NSE bulk/block prints and bhavcopy delivery percentage. Identifies institutional accumulation before markups and warns of churn/distribution traps.",
    where_used: "Watchlist Table (🏦 Badge), On Deck Cards, Help Guide",
    anchor: "glossary-instfootprint"
  },
  "Event Radar": {
    short: "Calendar radar tracking AGMs, IPO lock-in expiries, record dates, dividends, and quarterly earnings.",
    long: "Protects against overnight binary gap-risk. Blocks new entries within 5 calendar days of known events and warns on open positions within 3 days without altering stops.",
    where_used: "Watchlist Detail, Open Positions (🔔 Chip), Landmines Panel, Help Guide",
    anchor: "glossary-eventradar"
  },
  "Landmines": {
    short: "7-day chronological horizon of high-impact corporate binary events across all watchlist, on-deck, and open symbols.",
    long: "Consolidated warning dashboard displaying upcoming corporate actions that could cause unpredictable gap-downs or liquidity freezes.",
    where_used: "Near Buy (This Week's Landmines), Help Guide",
    anchor: "glossary-landmines"
  },
  "Deals Stale": {
    short: "Safety ribbon indicating that daily NSE bulk/block or delivery bhavcopy data is currently using a cached snapshot.",
    long: "Fail-open safety mechanism ensuring the scanner functions seamlessly during NSE exchange connectivity outages while transparently alerting the trader.",
    where_used: "Market Pulse Row, Help Guide",
    anchor: "glossary-dealsstale"
  },
  "Backtest": {
    short: "Rules-replay simulation engine importing and executing live production indicators, sizing, and exits across historical OHLCV bars.",
    long: "Strict zero-drift replay of main.py logic. Verifies win rate, profit factor, expectancy, and small-cap tail capture over historical market regimes.",
    where_used: "Backtest Tab, Help Guide",
    anchor: "glossary-backtest"
  },
  "Tail Capture": {
    short: "Asymmetric exit rule taking 50% partial at +2R and riding the remaining 50% along the 20-EMA trail.",
    long: "Proof of the small-cap momentum thesis: letting high-conviction winners trend past +2R with an EMA20 trailing stop generates substantial extra profit over mechanical target capping.",
    where_used: "Backtest (Tail-Capture Panel), Help Guide",
    anchor: "glossary-tailcapture"
  }
};

// Safe HTML Escaper
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Currency Formatter (INR)
function formatINR(val, includeSign = false) {
  if (val === null || val === undefined || isNaN(val)) return "N/A";
  const absVal = Math.abs(val);
  const formatted = "₹" + absVal.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (includeSign) {
    return val > 0 ? `+${formatted}` : val < 0 ? `-${formatted}` : formatted;
  }
  return val < 0 ? `-${formatted}` : formatted;
}

// Format Date
function formatDate(dateStr) {
  if (!dateStr) return "N/A";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

// Format Datetime
function formatDateTime(isoStr) {
  if (!isoStr) return "Unknown";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    }) + " IST";
  } catch {
    return isoStr;
  }
}

// =====================================================================
// DATA LAYER: PROXY-AWARE loadFile(name) WITH LOCALSTORAGE CACHE
// =====================================================================

function stopLoadingStates(statusCode) {
  const codeStr = statusCode || "Error";

  // Stop header chips
  const lastUpdatedEl = document.getElementById("lastUpdatedText");
  if (lastUpdatedEl && lastUpdatedEl.textContent.includes("Loading")) {
    lastUpdatedEl.textContent = `Updated: Data link error (${codeStr})`;
    lastUpdatedEl.style.display = "inline-block";
  }
  const mktBadge = document.getElementById("marketBadge");
  if (mktBadge && mktBadge.textContent.includes("Checking")) {
    mktBadge.textContent = "Data Link Error";
    mktBadge.className = "badge badge-danger";
  }
  const indexChip = document.getElementById("indexPriceChip");
  if (indexChip && indexChip.textContent.includes("Loading")) {
    indexChip.textContent = `Index: ${codeStr}`;
  }
  const closeChip = document.getElementById("lastCloseChip");
  if (closeChip && closeChip.textContent.includes("Loading")) {
    closeChip.textContent = "Last close: N/A";
  }

  // Stop tables
  const watchlistBody = document.getElementById("watchlistBody");
  if (watchlistBody && watchlistBody.querySelector(".skeleton-row")) {
    watchlistBody.innerHTML = `<tr><td colspan="9" class="empty-state" style="color: var(--bad);">Data link error (${codeStr}) — unable to fetch scan results</td></tr>`;
  }
  const openPosBody = document.getElementById("openPositionsBody");
  if (openPosBody && openPosBody.innerHTML.includes("Loading")) {
    openPosBody.innerHTML = `<tr><td colspan="12" class="empty-state" style="color: var(--bad);">Data link error (${codeStr}) — unable to fetch open positions</td></tr>`;
  }
  const histBody = document.getElementById("historyBody");
  if (histBody && histBody.innerHTML.includes("Loading")) {
    histBody.innerHTML = `<tr><td colspan="12" class="empty-state" style="color: var(--bad);">Data link error (${codeStr}) — unable to fetch trade history</td></tr>`;
  }
  const btEmpty = document.getElementById("btEmptyState");
  if (btEmpty && btEmpty.innerHTML.includes("Loading")) {
    btEmpty.innerHTML = `<span>⚠️ Data link error (${codeStr})</span>`;
  }

  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    refreshBtn.disabled = false;
    refreshBtn.textContent = "🔄 Refresh";
  }
}

function showDataLinkError(statusCode) {
  const codeStr = statusCode || "Network Error";
  const banner = document.getElementById("dataLinkErrorBanner");
  if (banner) {
    const msg = codeStr === "404"
      ? "Data file not found (404) — awaiting first automated scan in repo"
      : `Data link error (HTTP ${codeStr}) — unable to connect to GitHub`;
    banner.innerHTML = `<span>⚠️</span><span>${msg}</span>`;
    banner.style.display = "flex";
  }
  stopLoadingStates(codeStr);
}

function hideDataLinkError() {
  const banner = document.getElementById("dataLinkErrorBanner");
  if (banner) {
    banner.style.display = "none";
  }
  const chip = document.getElementById("cachedCopyChip");
  if (chip) {
    chip.style.display = "none";
  }
}

function showCachedCopyChip(timestamp) {
  const chip = document.getElementById("cachedCopyChip");
  if (chip) {
    let timeStr = "";
    if (timestamp) {
      try {
        const d = new Date(timestamp);
        timeStr = !isNaN(d.getTime())
          ? d.toLocaleDateString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
          : String(timestamp);
      } catch {
        timeStr = String(timestamp);
      }
    }
    chip.textContent = timeStr ? `cached copy (${timeStr})` : "cached copy";
    chip.style.display = "inline-flex";
  }
}

// Single data layer fetching public raw GitHub URL directly (anonymous, no headers)
async function loadFile(name) {
  const cleanName = String(name || "").replace(/^\/+/, "").trim();
  const url = `https://raw.githubusercontent.com/${OWNER}/${REPO}/main/${encodeURIComponent(cleanName)}`;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();

    // Cache every successful payload to localStorage keyed by name+updated_at
    const updatedAt = (payload && payload.updated_at) ? payload.updated_at : new Date().toISOString();
    const cacheKey = `cached_${cleanName}_${updatedAt}`;
    try {
      localStorage.setItem(cacheKey, JSON.stringify(payload));
      localStorage.setItem(`cached_${cleanName}_latest_key`, cacheKey);
      localStorage.setItem(`cached_${cleanName}_latest_time`, updatedAt);
      localStorage.setItem(`cached_${cleanName}`, JSON.stringify(payload));
    } catch (e) {
      console.warn("localStorage quota exceeded writing cache:", e);
    }
    return payload;
  } catch (err) {
    const statusMatch = err && err.message && err.message.match(/HTTP (\d+)/);
    const status = statusMatch ? statusMatch[1] : "Network Error";
    console.warn(`Direct fetch failed for ${cleanName} (${status}):`, err.message);
    return handleLoadFallback(cleanName, status);
  }
}

function handleLoadFallback(cleanName, statusCode) {
  // 1. STOP any "Loading..." state
  stopLoadingStates(statusCode);

  // 2. Show red #dataLinkError banner
  showDataLinkError(statusCode);

  // 3. Fallback to localStorage previous good payload
  let cachedPayload = null;
  let timestamp = null;

  const latestKey = localStorage.getItem(`cached_${cleanName}_latest_key`);
  if (latestKey) {
    const raw = localStorage.getItem(latestKey);
    if (raw) {
      try {
        cachedPayload = JSON.parse(raw);
        timestamp = localStorage.getItem(`cached_${cleanName}_latest_time`);
      } catch (e) {}
    }
  }

  if (!cachedPayload) {
    const rawDirect = localStorage.getItem(`cached_${cleanName}`);
    if (rawDirect) {
      try {
        cachedPayload = JSON.parse(rawDirect);
        timestamp = cachedPayload.updated_at || null;
      } catch (e) {}
    }
  }

  // Legacy fallback keys
  if (!cachedPayload) {
    if (cleanName === "scan_results.json") {
      const raw = localStorage.getItem("cached_scan_data");
      if (raw) {
        try {
          cachedPayload = JSON.parse(raw);
          timestamp = cachedPayload.updated_at || null;
        } catch (e) {}
      }
    } else if (cleanName === "open_positions.json") {
      const raw = localStorage.getItem("cached_open_positions");
      if (raw) {
        try { cachedPayload = JSON.parse(raw); } catch (e) {}
      }
    } else if (cleanName === "trades.json") {
      const raw = localStorage.getItem("cached_trades");
      if (raw) {
        try { cachedPayload = JSON.parse(raw); } catch (e) {}
      }
    }
  }

  if (cachedPayload) {
    showCachedCopyChip(timestamp);
    return cachedPayload;
  }

  // Never a blank infinite spinner
  return null;
}

// FetchJson helper delegating to loadFile
async function fetchJson(url) {
  if (url.includes("file=")) {
    const m = url.match(/file=([^&]+)/);
    if (m) return await loadFile(decodeURIComponent(m[1]));
  }
  const match = url.match(/([a-zA-Z0-9_.-]+\.json)$/);
  if (match) {
    return await loadFile(match[1]);
  }
  return await loadFile(url);
}

// Attempt to fetch live price for a symbol via Yahoo Chart API
async function fetchLivePrice(symbol) {
  try {
    const sym = symbol.endsWith(".NS") ? symbol : `${symbol}.NS`;
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${sym}?interval=1d&range=5d`;
    const res = await fetch(url, { mode: "cors" });
    if (!res.ok) return null;
    const data = await res.json();
    const meta = data?.chart?.result?.[0]?.meta;
    return meta?.regularMarketPrice || null;
  } catch {
    return null; // CORS or network blocked
  }
}

// =====================================================================
// DATA RENDERING
// =====================================================================

// =====================================================================
// TODAY'S ACTION PLAN GENERATOR
// =====================================================================
let _cachedScanData = null;
let _cachedOpenPositions = [];

function renderTodaysPlan(scanData, openPositions) {
  const planContainer = document.getElementById("todaysPlanCard");
  const bulletsList = document.getElementById("todaysPlanBullets");
  const planMetaTime = document.getElementById("planMetaTime");
  const planStatusPill = document.getElementById("planStatusPill");

  if (!planContainer || !bulletsList) return;

  if (scanData) _cachedScanData = scanData;
  if (openPositions) _cachedOpenPositions = openPositions;

  const currentScan = scanData || _cachedScanData;
  const currentPositions = openPositions || _cachedOpenPositions || [];

  if (planMetaTime && currentScan && currentScan.updated_at) {
    planMetaTime.textContent = `Scan Date: ${formatDateTime(currentScan.updated_at)}`;
  }

  const bullets = [];
  const isMarketOk = Boolean(currentScan && currentScan.market_ok);

  // 1. Market state bullet
  if (!isMarketOk) {
    bullets.push("Market defensive: no new entries today - cash is a position.");
  } else {
    bullets.push("Market uptrend confirmed: entries allowed for high-conviction Grade A/A+ setups.");
  }

  // 2. Count of A+/A grades
  const watchlist = (currentScan && currentScan.watchlist) || [];
  const topGradeItems = watchlist.filter(item => {
    const g = String(item.grade ?? item.Grade ?? "").toUpperCase();
    return g === "A+" || g === "A";
  });

  if (topGradeItems.length > 0) {
    const syms = topGradeItems.map(i => i.Symbol || "").filter(Boolean);
    bullets.push(`${topGradeItems.length} A-grade setup${topGradeItems.length > 1 ? "s" : ""}: ${syms.join(", ")} - review their charts before entry.`);
  }

  // 3. Open positions near stop or target
  let positionActions = 0;
  let nearStopCount = 0;
  if (Array.isArray(currentPositions) && currentPositions.length > 0) {
    currentPositions.forEach(pos => {
      const sym = pos.symbol || pos.Symbol || "Position";
      const entry = parseFloat(pos.entry_price || pos.Entry || 0);
      const stop = pos.stop ? parseFloat(pos.stop) : null;
      const target = pos.target ? parseFloat(pos.target) : null;
      const curPrice = parseFloat(pos._live_price || pos.last_price || pos.Close || entry);

      let nearStop = pos._is_near_stop;
      if (nearStop === undefined && stop && curPrice > 0) {
        const pctToStop = ((curPrice - stop) / curPrice) * 100;
        nearStop = (pctToStop <= 2.0);
      }
      if (nearStop) {
        bullets.push(`Defend or exit ${sym} - price near stop.`);
        positionActions++;
        nearStopCount++;
      }

      let nearTarget = pos._is_near_target;
      if (nearTarget === undefined && target && curPrice > 0) {
        const pctToTarget = ((target - curPrice) / curPrice) * 100;
        nearTarget = (pctToTarget <= 2.0);
      }
      if (nearTarget) {
        bullets.push(`Consider booking part of ${sym} near target.`);
        positionActions++;
      }
    });
  }

  // 3b. Institutional Moat highlights
  if (currentScan && currentScan.inst_summary && currentScan.inst_summary.accumulation_count > 0) {
    const accSyms = currentScan.inst_summary.symbols_accumulating || [];
    if (accSyms.length > 0) {
      bullets.push(`🏦 Institutional accumulation detected in ${accSyms.join(", ")} (rising delivery % / prints).`);
    }
  }

  // 3c. Event Radar Warnings for open positions
  if (Array.isArray(currentPositions)) {
    currentPositions.forEach(pos => {
      const sym = pos.symbol || pos.Symbol || "Position";
      const ev = pos.next_event || (currentScan?.landmines?.find(l => l.symbol === sym));
      if (pos.warn_event || (ev && ev.days_to_event != null && ev.days_to_event <= 3)) {
        bullets.push(`🔔 ${sym} event (${ev?.type || 'EVENT'}) in ${ev?.days_to_event ?? '≤3'} days - review hold.`);
      }
    });
  }

  // 4. Fallback if nothing applies
  if (topGradeItems.length === 0 && positionActions === 0) {
    bullets.push("No action needed. Review again after tomorrow's 4:15 PM scan.");
  }

  // Status pill update
  if (planStatusPill) {
    if (!isMarketOk) {
      planStatusPill.className = "badge badge-danger";
      planStatusPill.textContent = "Defensive Cash";
    } else if (nearStopCount > 0) {
      planStatusPill.className = "badge badge-warning";
      planStatusPill.textContent = "Defense Required";
    } else if (topGradeItems.length > 0) {
      planStatusPill.className = "badge badge-success";
      planStatusPill.textContent = `${topGradeItems.length} Setup${topGradeItems.length > 1 ? "s" : ""} Ready`;
    } else {
      planStatusPill.className = "badge badge-neutral";
      planStatusPill.textContent = "Standing By";
    }
  }

  // Render bullets list
  bulletsList.innerHTML = bullets.map(b => `
    <li class="todays-plan-item">
      <span class="todays-plan-bullet-icon">•</span>
      <span class="todays-plan-bullet-text">${escapeHtml(b)}</span>
    </li>
  `).join("");
}

// =====================================================================
// SC-3: DIAGNOSTIC MARKET PULSE, LEADERS BOARD & ON DECK
// =====================================================================

function updateIstLiveChip() {
  const istChip = document.getElementById("istLiveChip");
  if (!istChip) return;

  const now = new Date();
  // Client UTC time to IST (UTC + 5:30)
  const utcMs = now.getTime() + (now.getTimezoneOffset() * 60000);
  const istDate = new Date(utcMs + (330 * 60000));
  const day = istDate.getDay(); // 0 = Sun, 1 = Mon, ..., 6 = Sat
  const hrs = istDate.getHours();
  const mins = istDate.getMinutes();
  const curMins = hrs * 60 + mins;
  const openMins = 9 * 60 + 15;   // 9:15 AM
  const closeMins = 15 * 60 + 30; // 3:30 PM (15:30)

  const isWeekday = day >= 1 && day <= 5;
  const isOpen = isWeekday && curMins >= openMins && curMins < closeMins;

  if (isOpen) {
    istChip.className = "pulse-chip live-chip open";
    istChip.textContent = "🟢 MARKET OPEN 9:15-15:30 Mon-Fri";
  } else {
    istChip.className = "pulse-chip live-chip closed";
    let nextDay = "Mon";
    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    if (day >= 1 && day <= 4) {
      nextDay = curMins < openMins ? dayNames[day] : dayNames[day + 1];
    } else if (day === 5) {
      nextDay = curMins < openMins ? "Fri" : "Mon";
    } else {
      nextDay = "Mon";
    }
    istChip.textContent = `⚪ CLOSED - next open ${nextDay} 9:15`;
  }
}

function renderMarketPulse(scanData) {
  const marketBadge = document.getElementById("marketBadge");
  const indexChip = document.getElementById("indexPriceChip");
  const lastCloseChip = document.getElementById("lastCloseChip");
  const breadthChip = document.getElementById("breadthChip");
  const staleChip = document.getElementById("dataStaleChip");

  // 1. Regime Badge
  if (marketBadge) {
    if (scanData && scanData.market_ok) {
      marketBadge.className = "badge badge-success term-lookup";
      marketBadge.setAttribute("data-term", "Market regime");
      marketBadge.textContent = "Market: Uptrend";
    } else if (scanData) {
      marketBadge.className = "badge badge-danger term-lookup";
      marketBadge.setAttribute("data-term", "Market regime");
      marketBadge.textContent = "Market: Defensive";
    } else {
      marketBadge.className = "badge badge-neutral term-lookup";
      marketBadge.setAttribute("data-term", "Market regime");
      marketBadge.textContent = "Checking Market...";
    }
  }

  const ms = scanData ? scanData.market_summary : null;

  // 2. Index Price Chip ("<source> last ₹x (±y%)")
  if (indexChip) {
    if (ms && ms.last_close != null) {
      const srcName = ms.source === "^NSEI" ? "NIFTY 50" : (ms.source || "NIFTY 50");
      const sign = (ms.chg_pct >= 0) ? "+" : "";
      const chgColor = (ms.chg_pct >= 0) ? "var(--success)" : "var(--danger)";
      const formattedClose = Number(ms.last_close).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      indexChip.innerHTML = `${escapeHtml(srcName)} last ₹${formattedClose} (<span style="color: ${chgColor}; font-weight: 700;">${sign}${Number(ms.chg_pct).toFixed(2)}%</span>)`;
    } else {
      indexChip.textContent = "NIFTY 50 last --";
    }
  }

  // 3. Last Close Chip ("Last close: <date> 3:30 PM IST")
  if (lastCloseChip) {
    if (ms && ms.last_bar_date) {
      lastCloseChip.textContent = `Last close: ${ms.last_bar_date} 3:30 PM IST`;
    } else if (scanData && scanData.updated_at) {
      lastCloseChip.textContent = `Last close: ${scanData.updated_at.slice(0, 10)} 3:30 PM IST`;
    } else {
      lastCloseChip.textContent = "Last close: --";
    }
  }

  // 4. Live IST Chip
  updateIstLiveChip();

  // 5. Breadth Line
  if (breadthChip) {
    if (ms && ms.breadth_above_sma50 != null) {
      breadthChip.textContent = `Breadth: ${ms.breadth_above_sma50}% > SMA50 | ${ms.breadth_above_sma200}% > SMA200 (${ms.advancers} Adv / ${ms.decliners} Dec)`;
    } else {
      breadthChip.textContent = "Breadth: --";
    }
  }

  // 6. Amber DATA STALE if as_of > 36h on a weekday
  if (staleChip) {
    let isStale = false;
    const now = new Date();
    const utcMs = now.getTime() + (now.getTimezoneOffset() * 60000);
    const istDate = new Date(utcMs + (330 * 60000));
    const day = istDate.getDay();
    const isWeekday = day >= 1 && day <= 5;

    if (isWeekday) {
      let dataTime = null;
      if (scanData && scanData.updated_at) {
        dataTime = new Date(scanData.updated_at).getTime();
      } else if (ms && ms.last_bar_date) {
        dataTime = new Date(`${ms.last_bar_date}T15:30:00+05:30`).getTime();
      }
      if (dataTime && !isNaN(dataTime)) {
        const diffHours = (now.getTime() - dataTime) / (1000 * 3600);
        if (diffHours > 36) {
          isStale = true;
        }
      }
    }
    staleChip.style.display = isStale ? "inline-flex" : "none";
  }

  // 7. DEALS STALE Ribbon / Chip
  const dealsStaleChip = document.getElementById("dealsStaleChip");
  if (dealsStaleChip) {
    const isDealsStale = Boolean(scanData && scanData.deals_stale);
    dealsStaleChip.style.display = isDealsStale ? "inline-flex" : "none";
  }
}

function renderLeadersBoard(leaders) {
  const countBadge = document.getElementById("leadersCountBadge");
  const chipsRow = document.getElementById("leadersChipsRow");
  if (!chipsRow) return;

  const list = leaders || [];
  if (countBadge) {
    countBadge.textContent = `${list.length} Leader${list.length === 1 ? '' : 's'}`;
  }

  if (list.length === 0) {
    chipsRow.innerHTML = `<span class="text-dim" style="font-size: 12px; padding: 4px 6px;">No Stage-2 leaders currently qualified.</span>`;
    return;
  }

  chipsRow.innerHTML = list.map(item => {
    const sym = escapeHtml(item.symbol || "");
    const rs = item.rs_rating != null ? Math.round(Number(item.rs_rating)) : null;
    let rsClass = "rs-pill-gray";
    if (rs !== null && !isNaN(rs)) {
      if (rs >= 90) rsClass = "rs-pill-green";
      else if (rs >= 80) rsClass = "rs-pill-blue";
    }
    const rsText = rs !== null && !isNaN(rs) ? `RS ${rs}` : "RS n/a";
    const priceText = item.close != null ? formatINR(item.close) : "";
    const secText = item.sector ? escapeHtml(item.sector) : "";

    return `
      <div class="leader-chip term-lookup" data-term="Leaders Board" data-symbol="${sym}" title="Click to filter watchlist for ${sym}">
        <span class="leader-chip-sym"><strong>${sym}</strong></span>
        <span class="rs-pill ${rsClass}">${rsText}</span>
        <span class="leader-chip-price">${priceText}</span>
        ${secText ? `<span class="leader-chip-sector text-dim" style="font-size: 11px;">${secText}</span>` : ""}
      </div>
    `;
  }).join("");

  chipsRow.querySelectorAll(".leader-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const sym = chip.getAttribute("data-symbol");
      const searchInput = document.getElementById("watchlistSearchInput");
      if (searchInput && sym) {
        searchInput.value = sym;
        searchInput.dispatchEvent(new Event("input"));
        document.getElementById("watchlistTable")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
}

function renderOnDeck(onDeckList) {
  const countBadge = document.getElementById("onDeckCountBadge");
  const grid = document.getElementById("onDeckCardsGrid");
  if (!grid) return;

  const list = onDeckList || [];
  if (countBadge) {
    countBadge.textContent = `${list.length} Setup${list.length === 1 ? '' : 's'}`;
  }

  if (list.length === 0) {
    grid.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1; padding: 24px; text-align: center; color: var(--text-dim);">No near-miss candidates currently on deck. Candidates appear when satisfying Stage-2 Trend &amp; Squeeze criteria under resistance.</div>`;
    return;
  }

  grid.innerHTML = list.map(item => {
    const sym = escapeHtml(item.symbol || "");
    const dist = item.dist_pct != null ? Number(item.dist_pct).toFixed(2) : "0.00";
    const close = item.close != null ? formatINR(item.close) : "--";
    const breakoutLevel = item.breakout_level != null ? formatINR(item.breakout_level) : "--";
    const missing = escapeHtml(item.missing_condition || "TRIGGER");
    const atr = item.atr14 != null ? `₹${Number(item.atr14).toFixed(2)}` : "--";
    const rsi = item.rsi14 != null ? Number(item.rsi14).toFixed(1) : "--";

    // Institutional Footprint
    const instFp = item.inst_footprint || "unknown";
    let instBadge = "";
    if (instFp === "accumulation") {
      instBadge = `<span class="inst-pill inst-pill-acc" title="Institutional Accumulation">🏦 ACCUM</span>`;
    } else if (instFp === "churn") {
      instBadge = `<span class="inst-pill inst-pill-churn" title="Institutional Churn">⚠️ CHURN</span>`;
    } else {
      instBadge = `<span class="inst-pill inst-pill-unk" title="Institutional Footprint: Unknown">⚪ UNK</span>`;
    }

    // Event Radar Chip
    let eventChip = "";
    if (item.next_event && item.next_event.days_to_event != null && item.next_event.days_to_event <= 7) {
      const d = item.next_event.days_to_event;
      const t = escapeHtml(item.next_event.type || "EVENT");
      eventChip = `<span class="badge badge-warning warn-event-chip" style="font-size: 10px;">🔔 ${t} ${d}d</span>`;
    }

    return `
      <div class="on-deck-card" data-symbol="${sym}">
        <div class="on-deck-card-header">
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <strong class="on-deck-symbol">${sym}</strong>
            <span class="badge badge-warning" style="font-size: 11px; font-weight: 700;">${dist}% to pivot</span>
            ${instBadge}
            ${eventChip}
          </div>
          <span class="badge badge-neutral" style="font-size: 11px;" title="Condition required to trigger buy signal">Awaiting: ${missing}</span>
        </div>

        <div class="on-deck-metrics" style="display: flex; align-items: center; justify-content: space-between; font-size: 12.5px; margin-top: 6px; flex-wrap: wrap; gap: 8px;">
          <div><span class="text-dim">Close:</span> <strong>${close}</strong></div>
          <div><span class="text-dim">Pivot:</span> <strong>${breakoutLevel}</strong></div>
          <div><span class="badge badge-neutral" title="Average True Range (14)">ATR ${atr}</span></div>
          <div><span class="badge badge-neutral" title="Relative Strength Index (14)">RSI ${rsi}</span></div>
        </div>

        <div style="display: flex; gap: 8px; margin-top: 10px;">
          <button class="btn btn-secondary btn-sm on-deck-chart-btn" data-symbol="${sym}" data-breakout="${item.breakout_level || ''}" style="flex: 1; min-height: 44px; display: inline-flex; align-items: center; justify-content: center; gap: 6px;">
            <span>📈 View 60-Bar Sparkline</span>
          </button>
          <button class="btn btn-outline-primary btn-sm on-deck-size-btn" data-symbol="${sym}" data-close="${item.close || ''}" data-atr="${item.atr14 || ''}" style="min-height: 44px; padding: 0 16px;">
            <span>Size</span>
          </button>
        </div>

        <div id="onDeckChartBox-${sym}" style="display: none; margin-top: 10px; background: rgba(0,0,0,0.25); border-radius: 8px; padding: 10px; border: 1px solid rgba(255,255,255,0.06);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-size: 11px; font-weight: 600; color: #fff;">60-Bar Tightening Sparkline</span>
            <span id="onDeckChartMeta-${sym}" style="font-size: 11px; color: var(--text-dim);">Loading candles...</span>
          </div>
          <canvas id="onDeckCanvas-${sym}" style="width: 100%; height: 180px; display: block;"></canvas>
        </div>
      </div>
    `;
  }).join("");

  // Attach button events
  grid.querySelectorAll(".on-deck-size-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const sym = btn.getAttribute("data-symbol");
      const c = parseFloat(btn.getAttribute("data-close")) || 0;
      const a = parseFloat(btn.getAttribute("data-atr")) || 0;
      openPositionSizerFor({ Symbol: sym, Close: c, ATR14: a });
    });
  });

  grid.querySelectorAll(".on-deck-chart-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const sym = btn.getAttribute("data-symbol");
      const breakoutLevel = parseFloat(btn.getAttribute("data-breakout")) || 0;
      const box = document.getElementById(`onDeckChartBox-${sym}`);
      const meta = document.getElementById(`onDeckChartMeta-${sym}`);
      const canvas = document.getElementById(`onDeckCanvas-${sym}`);
      if (!box || !canvas) return;

      const isHidden = box.style.display === "none";
      box.style.display = isHidden ? "block" : "none";
      const spanText = btn.querySelector("span");
      if (spanText) {
        spanText.textContent = isHidden ? "📉 Hide Sparkline" : "📈 View 60-Bar Sparkline";
      }

      if (isHidden && !canvas._loaded) {
        try {
          if (meta) meta.textContent = "Fetching 60-bar candles...";
          const chartData = await fetchChartData(sym);
          if (!chartData || !chartData.chart || !chartData.chart.result || chartData.chart.result.length === 0) {
            if (meta) meta.textContent = "Chart unavailable";
            return;
          }
          const res = chartData.chart.result[0];
          const timestamps = res.timestamp || [];
          const quote = res.indicators?.quote?.[0] || {};
          const candles = [];
          for (let i = 0; i < timestamps.length; i++) {
            const o = quote.open?.[i];
            const h = quote.high?.[i];
            const l = quote.low?.[i];
            const c = quote.close?.[i];
            const v = quote.volume?.[i] || 0;
            if (o != null && h != null && l != null && c != null && !isNaN(c)) {
              candles.push({ time: timestamps[i], open: o, high: h, low: l, close: c, volume: v });
            }
          }
          const last60 = candles.slice(-60);
          if (last60.length === 0) {
            if (meta) meta.textContent = "No candle data";
            return;
          }
          drawMiniChart(canvas, last60, breakoutLevel || last60[last60.length - 1].close, sym);
          canvas._loaded = true;
          if (meta) meta.textContent = `${last60.length} bars • Pivot: ₹${(breakoutLevel || 0).toFixed(2)}`;
        } catch (err) {
          if (meta) meta.textContent = "Error loading chart";
        }
      }
    });
  });
}

function initCollapsibleSections() {
  const leadersBtn = document.getElementById("leadersToggleBtn");
  const leadersContent = document.getElementById("leadersContent");
  const leadersChevron = document.getElementById("leadersChevron");
  if (leadersBtn && leadersContent) {
    leadersBtn.addEventListener("click", () => {
      const isExpanded = leadersBtn.getAttribute("aria-expanded") === "true";
      leadersBtn.setAttribute("aria-expanded", !isExpanded);
      leadersContent.style.display = isExpanded ? "none" : "block";
      if (leadersChevron) leadersChevron.textContent = isExpanded ? "▶" : "▼";
    });
  }

  const onDeckBtn = document.getElementById("onDeckToggleBtn");
  const onDeckContent = document.getElementById("onDeckContent");
  const onDeckChevron = document.getElementById("onDeckChevron");
  if (onDeckBtn && onDeckContent) {
    onDeckBtn.addEventListener("click", () => {
      const isExpanded = onDeckBtn.getAttribute("aria-expanded") === "true";
      onDeckBtn.setAttribute("aria-expanded", !isExpanded);
      onDeckContent.style.display = isExpanded ? "none" : "block";
      if (onDeckChevron) onDeckChevron.textContent = isExpanded ? "▶" : "▼";
    });
  }

  const landminesBtn = document.getElementById("landminesToggleBtn");
  const landminesContent = document.getElementById("landminesContent");
  const landminesChevron = document.getElementById("landminesChevron");
  if (landminesBtn && landminesContent) {
    landminesBtn.addEventListener("click", () => {
      const isExpanded = landminesBtn.getAttribute("aria-expanded") === "true";
      landminesBtn.setAttribute("aria-expanded", !isExpanded);
      landminesContent.style.display = isExpanded ? "none" : "block";
      if (landminesChevron) landminesChevron.textContent = isExpanded ? "▶" : "▼";
    });
  }
}

function renderLandmines(landmines) {
  const section = document.getElementById("landminesSection");
  const grid = document.getElementById("landminesGrid");
  const countBadge = document.getElementById("landminesCountBadge");
  if (!section || !grid) return;

  const list = landmines || [];
  if (countBadge) {
    countBadge.textContent = `${list.length} Event${list.length === 1 ? '' : 's'}`;
    countBadge.className = list.length > 0 ? "badge badge-danger" : "badge badge-neutral";
  }

  section.style.display = "block";

  if (list.length === 0) {
    grid.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1; padding: 16px; text-align: center; color: var(--text-dim);">🛡️ Clear radar: No corporate actions (AGM/Lock-in/Record/Earnings) scheduled in the next 7 days for active watchlist or open positions.</div>`;
    return;
  }

  grid.innerHTML = list.map(item => {
    const sym = escapeHtml(item.symbol || "");
    const type = escapeHtml(item.type || "EVENT");
    const date = escapeHtml(item.date || "");
    const days = item.days_to_event != null ? Number(item.days_to_event) : "--";
    const note = escapeHtml(item.note || "");
    const daysLabel = days === 0 ? "TODAY" : `${days}d away`;

    return `
      <div class="landmine-item" data-symbol="${sym}">
        <div class="landmine-item-header">
          <div style="display: flex; align-items: center; gap: 8px;">
            <strong style="font-size: 14px; color: #fff;">${sym}</strong>
            <span class="landmine-type-badge">${type}</span>
          </div>
          <span class="landmine-days-badge">${daysLabel}</span>
        </div>
        <div style="font-size: 12px; color: var(--text-dim); display: flex; justify-content: space-between;">
          <span>Event Date: <strong>${date}</strong></span>
          <span style="color: var(--warning);">High Gap-Risk</span>
        </div>
        ${note ? `<div style="font-size: 11.5px; color: var(--text-muted); line-height: 1.3;">${note}</div>` : ""}
      </div>
    `;
  }).join("");
}

// 1. Render Tab: Near Buy (Watchlist & Active Signals)
function renderNearBuy(scanData, openPositions) {
  // Render Market Pulse row (SC-3 diagnostic telemetry)
  renderMarketPulse(scanData);

  // Render Today's Plan box
  renderTodaysPlan(scanData, openPositions);

  if (!scanData) {
    document.getElementById("watchlistBody").innerHTML = `
      <tr><td colspan="9" class="empty-state">No scan results found on GitHub repository.</td></tr>
    `;
    renderLeadersBoard([]);
    renderOnDeck([]);
    return;
  }

  // Render Leaders Board (SC-3)
  renderLeadersBoard(scanData.leaders_board || []);

  const regimeBanner = document.getElementById("regimeBanner");
  const regimeText = document.getElementById("regimeText");
  const scannedMeta = document.getElementById("scannedMeta");
  const lastUpdated = document.getElementById("lastUpdatedText");

  // Update header metadata
  if (lastUpdated) lastUpdated.textContent = `Updated: ${formatDateTime(scanData.updated_at)}`;

  if (scanData.market_ok) {
    regimeBanner.className = "regime-banner uptrend";
    regimeText.textContent = "🟢 MARKET UPTREND CONFIRMED: Normal buy entry rules active.";
  } else {
    regimeBanner.className = "regime-banner defensive";
    regimeText.textContent = "🔴 MARKET FILTER ACTIVE: Index in pullback/downtrend. New entry signals blocked (O'Neil M-rule).";
  }
  scannedMeta.textContent = `${scanData.scanned_count || 100} Small Cap stocks scanned`;
  regimeBanner.style.display = "flex";

  // Render Signals if present
  const signalsContainer = document.getElementById("signalsContainer");
  const signalsBody = document.getElementById("signalsBody");
  if (scanData.signals && scanData.signals.length > 0) {
    signalsContainer.style.display = "block";
    signalsBody.innerHTML = scanData.signals.map(s => `
      <tr class="row-green">
        <td data-label="Type"><span class="badge badge-success">${s.Type || "BREAKOUT"}</span></td>
        <td data-label="Symbol"><strong>${s.Symbol}</strong></td>
        <td data-label="Entry">${formatINR(s.Entry)}</td>
        <td data-label="Stop" style="color: var(--danger);">${formatINR(s.Stop)}</td>
        <td data-label="Target" style="color: var(--success);">${formatINR(s.Target)}</td>
        <td data-label="Qty">${s.Qty}</td>
        <td data-label="Risk Amount">${formatINR(s["Risk Amount"])}</td>
        <td data-label="Sector"><span class="badge badge-neutral">${s.Sector || "N/A"}</span></td>
      </tr>
    `).join("");
  } else {
    signalsContainer.style.display = "none";
  }

  // Render Sector Leadership Strip & Watchlist Filters (Phase 1)
  const watchlist = scanData.watchlist || [];
  initWatchlistFilterListeners();
  renderSectorLeadership(watchlist);
  applyWatchlistFiltering(watchlist, scanData);

  // Render On Deck candidates (SC-3)
  renderOnDeck(scanData.on_deck || []);

  // Render Landmines Panel (SC-4)
  renderLandmines(scanData.landmines || []);
}

// Module state for Watchlist Filter & Sort (Phase 1)
let _wlSelectedFilter = "all";
let _wlSelectedSector = null;
let _wlSearchQuery = "";
let _wlSortMode = "score_desc";
let _wlFiltersInitialized = false;

// 1. Render Sector Leadership & Rotation Strip (Item #2)
function renderSectorLeadership(watchlist) {
  const strip = document.getElementById("sectorLeadershipStrip");
  const container = document.getElementById("sectorChipsContainer");
  const badge = document.getElementById("sectorActiveFilterBadge");
  const filterName = document.getElementById("sectorFilterName");
  if (!strip || !container) return;

  if (!watchlist || watchlist.length === 0) {
    strip.style.display = "none";
    return;
  }

  // Aggregate by Sector
  const sectorMap = {};
  for (const item of watchlist) {
    const sec = (item.Sector || "^NSEI").trim();
    if (!sectorMap[sec]) {
      sectorMap[sec] = { count: 0, gradeA: 0, isBullish: false };
    }
    sectorMap[sec].count++;
    const grade = item.grade ?? item.Grade ?? "C";
    if (grade === "A+" || grade === "A") {
      sectorMap[sec].gradeA++;
    }
    if (item.SectorBullish === "YES") {
      sectorMap[sec].isBullish = true;
    }
  }

  const sectors = Object.keys(sectorMap).sort((a, b) => {
    if (sectorMap[b].count !== sectorMap[a].count) {
      return sectorMap[b].count - sectorMap[a].count;
    }
    return sectorMap[b].gradeA - sectorMap[a].gradeA;
  });

  if (sectors.length === 0) {
    strip.style.display = "none";
    return;
  }

  strip.style.display = "block";

  if (_wlSelectedSector && badge && filterName) {
    filterName.textContent = _wlSelectedSector;
    badge.style.display = "inline-flex";
  } else if (badge) {
    badge.style.display = "none";
  }

  container.innerHTML = sectors.map(sec => {
    const data = sectorMap[sec];
    const isSelected = _wlSelectedSector === sec;
    const dot = data.isBullish ? "🟢" : "🔴";
    const gradeTag = data.gradeA > 0 ? `<span class="sec-chip-grade">${data.gradeA} A</span>` : "";
    return `
      <button class="sector-chip ${isSelected ? 'active' : ''}" data-sector="${escapeHtml(sec)}" title="${data.isBullish ? 'Sector in Stage 2 Uptrend' : 'Sector in Pullback/Neutral'}">
        <span class="sec-chip-dot">${dot}</span>
        <span class="sec-chip-name">${escapeHtml(sec)}</span>
        <span class="sec-chip-count">${data.count}</span>
        ${gradeTag}
      </button>
    `;
  }).join("");

  container.querySelectorAll(".sector-chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const sec = btn.getAttribute("data-sector");
      if (_wlSelectedSector === sec) {
        _wlSelectedSector = null;
      } else {
        _wlSelectedSector = sec;
      }
      renderSectorLeadership(watchlist);
      applyWatchlistFiltering(watchlist, _cachedScanData);
    });
  });

  if (badge) {
    badge.onclick = () => {
      _wlSelectedSector = null;
      renderSectorLeadership(watchlist);
      applyWatchlistFiltering(watchlist, _cachedScanData);
    };
  }
}

// 2. Watchlist Filter & Sort State Manager (Item #1)
function applyWatchlistFiltering(watchlist, scanData) {
  const watchlistBody = document.getElementById("watchlistBody");
  if (!watchlistBody) return;

  if (!watchlist || watchlist.length === 0) {
    watchlistBody.innerHTML = `
      <tr><td colspan="9" class="empty-state">📋 Watchlist empty: no small caps currently in uptrend within 5% of breakout.</td></tr>
    `;
    updateFilterCounts([], 0);
    return;
  }

  const basePool = _wlSelectedSector ? watchlist.filter(w => (w.Sector || "^NSEI").trim() === _wlSelectedSector) : watchlist;
  updateFilterCounts(basePool, watchlist.length);

  let filtered = [...basePool];

  // Search filter
  if (_wlSearchQuery.trim() !== "") {
    const q = _wlSearchQuery.trim().toLowerCase();
    filtered = filtered.filter(item => {
      const sym = (item.Symbol || "").toLowerCase();
      const sec = (item.Sector || "").toLowerCase();
      return sym.includes(q) || sec.includes(q);
    });
  }

  // Chip filter
  if (_wlSelectedFilter === "grade_a") {
    filtered = filtered.filter(item => {
      const g = item.grade ?? item.Grade ?? "C";
      return g === "A+" || g === "A";
    });
  } else if (_wlSelectedFilter === "near_breakout") {
    filtered = filtered.filter(item => (parseFloat(item["DistToBreakout%"]) || 0) <= 2.0);
  } else if (_wlSelectedFilter === "coiling") {
    filtered = filtered.filter(item => item.Coiling === "YES");
  } else if (_wlSelectedFilter === "sector_bullish") {
    filtered = filtered.filter(item => item.SectorBullish === "YES");
  }

  // Sorting
  filtered.sort((a, b) => {
    const scoreA = Number(a.score ?? a.Score ?? 0);
    const scoreB = Number(b.score ?? b.Score ?? 0);
    const distA = parseFloat(a["DistToBreakout%"]) || 0;
    const distB = parseFloat(b["DistToBreakout%"]) || 0;
    const closeA = parseFloat(a.Close) || 0;
    const closeB = parseFloat(b.Close) || 0;
    const symA = (a.Symbol || "");
    const symB = (b.Symbol || "");

    switch (_wlSortMode) {
      case "dist_asc":
        return distA - distB;
      case "price_desc":
        return closeB - closeA;
      case "price_asc":
        return closeA - closeB;
      case "symbol_asc":
        return symA.localeCompare(symB);
      case "score_desc":
      default:
        if (scoreB !== scoreA) return scoreB - scoreA;
        return distA - distB;
    }
  });

  const statusEl = document.getElementById("watchlistCountStatus");
  const resetBtn = document.getElementById("resetWatchlistFiltersBtn");
  const isFiltered = _wlSelectedFilter !== "all" || Boolean(_wlSelectedSector) || _wlSearchQuery.trim() !== "";

  if (statusEl) {
    if (isFiltered) {
      statusEl.innerHTML = `Showing <strong>${filtered.length}</strong> of <strong>${watchlist.length}</strong> setups`;
    } else {
      statusEl.textContent = `Showing all ${watchlist.length} setups`;
    }
  }
  if (resetBtn) {
    resetBtn.style.display = isFiltered ? "inline-block" : "none";
  }

  if (filtered.length === 0) {
    watchlistBody.innerHTML = `
      <tr>
        <td colspan="9" class="empty-state">
          🔍 No setups match the current filters. 
          <a href="javascript:void(0)" onclick="resetAllWatchlistFilters()" style="color: #38bdf8; text-decoration: underline; margin-left: 6px;">Reset filters</a>
        </td>
      </tr>
    `;
    return;
  }

  watchlistBody.innerHTML = filtered.map(item => {
    const dist = parseFloat(item["DistToBreakout%"]) || 0;
    let rowClass = "";
    if (dist <= 2.0) rowClass = "row-green";
    else if (dist <= 5.0) rowClass = "row-yellow";

    const isBullish = item.SectorBullish === "YES";
    const bullishBadge = isBullish
      ? `<span class="badge badge-success term-lookup" data-term="Sector Bullish">YES</span>`
      : `<span class="badge badge-warning term-lookup" data-term="Sector Bullish">no</span>`;

    const coilingBadge = item.Coiling === "YES"
      ? `<span class="badge badge-success term-lookup" data-term="Coiling">Coiling</span>`
      : `<span class="badge badge-neutral term-lookup" data-term="Coiling">no</span>`;

    const score = Number(item.score ?? item.Score ?? 0);
    let scoreBadgeClass = "badge-danger";
    if (score >= 80) {
      scoreBadgeClass = "badge-success";
    } else if (score >= 60) {
      scoreBadgeClass = "badge-warning";
    }
    const scoreBadge = `<span class="badge ${scoreBadgeClass} term-lookup" data-term="Score">${score}</span>`;

    const grade = item.grade ?? item.Grade ?? "C";
    let gradeBadgeClass = "badge-neutral";
    if (grade === "A+" || grade === "A") gradeBadgeClass = "badge-success";
    else if (grade === "B") gradeBadgeClass = "badge-warning";
    else if (grade === "C") gradeBadgeClass = "badge-danger";
    const gradeBadge = `<span class="badge ${gradeBadgeClass} term-lookup" data-term="Grade">${grade}</span>`;

    const rawRs = item.rs_rating != null ? Number(item.rs_rating) : (item.RS_RATING != null ? Number(item.RS_RATING) : null);
    let rsBadge = "";
    if (rawRs !== null && !isNaN(rawRs)) {
      const rsVal = Math.round(rawRs);
      let rsClass = "rs-pill-gray";
      if (rsVal >= 90) rsClass = "rs-pill-green";
      else if (rsVal >= 80) rsClass = "rs-pill-blue";
      rsBadge = `<span class="rs-pill ${rsClass} term-lookup" data-term="RS Rating" title="Relative Strength Rating: ${rsVal}/99">RS ${rsVal}</span>`;
    } else {
      rsBadge = `<span class="rs-pill rs-pill-gray term-lookup" data-term="RS Rating" title="Relative Strength Rating not available">RS n/a</span>`;
    }

    // Institutional Footprint (A)
    const instFp = item.inst_footprint || "unknown";
    let instBadge = "";
    if (instFp === "accumulation") {
      instBadge = `<span class="inst-pill inst-pill-acc term-lookup" data-term="Institutional Footprint" title="Institutional Accumulation: Rising delivery % or recent block print">🏦 ACCUM</span>`;
    } else if (instFp === "churn") {
      instBadge = `<span class="inst-pill inst-pill-churn term-lookup" data-term="Institutional Footprint" title="Institutional Churn: High volume (≥1.5x) & low delivery (<25%)">⚠️ CHURN</span>`;
    } else {
      instBadge = `<span class="inst-pill inst-pill-unk term-lookup" data-term="Institutional Footprint" title="Institutional Footprint: Unknown / Insufficient deal prints">⚪ UNK</span>`;
    }

    // Event Radar Chip (B)
    let eventChip = "";
    if (item.next_event && item.next_event.days_to_event != null && item.next_event.days_to_event <= 7) {
      const d = item.next_event.days_to_event;
      const t = escapeHtml(item.next_event.type || "EVENT");
      const isBlocked = d <= 5;
      eventChip = `<span class="badge ${isBlocked ? 'badge-danger' : 'badge-warning'} warn-event-chip" style="font-size: 10px;" title="${isBlocked ? 'ENTRY GATE: Event within 5d blackout window' : 'Upcoming Event'}: ${t} in ${d}d">🔔 ${t} ${d}d</span>`;
    }

    // SC-6: Color Pills with WCAG-AA Contrast
    let gradePillClass = "pill-grade-c";
    if (grade === "A+") gradePillClass = "pill-grade-aplus";
    else if (grade === "A") gradePillClass = "pill-grade-a";
    else if (grade === "B") gradePillClass = "pill-grade-b";
    const gradePill = `<span class="pill ${gradePillClass} term-lookup" data-term="Grade">${grade}</span>`;

    let distPillClass = "pill-neutral";
    if (dist <= 1.0) distPillClass = "pill-success";
    else if (dist <= 2.0) distPillClass = "pill-primary";
    else if (dist <= 5.0) distPillClass = "pill-warning";
    const distPill = `<span class="pill ${distPillClass} term-lookup" data-term="Dist to Breakout">${dist.toFixed(2)}%</span>`;

    // Status Pill
    let statusPill = "";
    if (item.next_event && item.next_event.days_to_event != null && item.next_event.days_to_event <= 5) {
      statusPill = `<span class="pill pill-danger">🔴 Blackout (${item.next_event.days_to_event}d)</span>`;
    } else if (dist <= 1.0) {
      statusPill = `<span class="pill pill-success">🟢 Ready (${dist >= 0 ? '+' : ''}${dist.toFixed(1)}%)</span>`;
    } else if (dist <= 2.0) {
      statusPill = `<span class="pill pill-primary">🔵 Near Breakout</span>`;
    } else if (item.Coiling === "YES") {
      statusPill = `<span class="pill pill-warning">🟡 Coiling</span>`;
    } else {
      statusPill = `<span class="pill pill-neutral">⚪ Watchlist (${dist.toFixed(1)}%)</span>`;
    }

    return `
      <tr class="watchlist-row ${rowClass}" data-symbol="${item.Symbol}" title="Click to expand diagnosis, 6-month chart & GTT plan">
        <td data-label="Symbol">
          <div style="display: flex; align-items: center; gap: 8px;">
            <strong style="font-size: 13.5px; color: #fff;">${item.Symbol}</strong>
          </div>
        </td>
        <td data-label="Grade"><div style="display: flex; align-items: center; gap: 4px; flex-wrap: wrap;">${gradePill} ${rsBadge} ${instBadge} ${eventChip}</div></td>
        <td data-label="Close"><strong>${formatINR(item.Close)}</strong></td>
        <td data-label="Dist %">${distPill}</td>
        <td data-label="Status">${statusPill}</td>
        <td data-label="Score" class="hide-mobile">${scoreBadge}</td>
        <td data-label="Sector" class="hide-mobile"><span class="pill pill-neutral">${item.Sector || "^NSEI"}</span></td>
        <td data-label="Action">
          <button class="btn btn-xs btn-outline-primary size-trade-btn" data-symbol="${item.Symbol}" title="Size this trade with Position Sizer">
            Size
          </button>
        </td>
        <td style="text-align: right; width: 44px;">
          <span class="chevron" style="font-size: 11px; color: var(--text-dim); padding: 8px;">▼</span>
        </td>
      </tr>
    `;
  }).join("");

  // Attach click listeners for expandable details
  watchlistBody.querySelectorAll(".watchlist-row").forEach(row => {
    row.addEventListener("click", () => {
      const sym = row.getAttribute("data-symbol");
      const item = filtered.find(w => w.Symbol === sym);
      if (item) {
        toggleWatchlistDetail(row, item, scanData);
      }
    });
  });

  // Attach click listeners for "Size this trade" buttons on rows
  watchlistBody.querySelectorAll(".size-trade-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const sym = btn.getAttribute("data-symbol");
      const item = filtered.find(w => w.Symbol === sym);
      if (item) {
        openPositionSizerFor(item);
      }
    });
  });
}

function updateFilterCounts(pool, totalCount) {
  const elAll = document.getElementById("countAll");
  const elGradeA = document.getElementById("countGradeA");
  const elNearBreakout = document.getElementById("countNearBreakout");
  const elCoiling = document.getElementById("countCoiling");
  const elSecBullish = document.getElementById("countSectorBullish");

  if (elAll) elAll.textContent = pool.length;
  if (elGradeA) {
    const c = pool.filter(w => {
      const g = w.grade ?? w.Grade ?? "C";
      return g === "A+" || g === "A";
    }).length;
    elGradeA.textContent = c;
  }
  if (elNearBreakout) {
    const c = pool.filter(w => (parseFloat(w["DistToBreakout%"]) || 0) <= 2.0).length;
    elNearBreakout.textContent = c;
  }
  if (elCoiling) {
    const c = pool.filter(w => w.Coiling === "YES").length;
    elCoiling.textContent = c;
  }
  if (elSecBullish) {
    const c = pool.filter(w => w.SectorBullish === "YES").length;
    elSecBullish.textContent = c;
  }
}

function initWatchlistFilterListeners() {
  if (_wlFiltersInitialized) return;
  _wlFiltersInitialized = true;

  const searchInput = document.getElementById("watchlistSearchInput");
  const clearBtn = document.getElementById("clearWatchlistSearchBtn");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      _wlSearchQuery = searchInput.value;
      if (clearBtn) clearBtn.style.display = _wlSearchQuery ? "inline-block" : "none";
      if (_cachedScanData) applyWatchlistFiltering(_cachedScanData.watchlist || [], _cachedScanData);
    });
  }
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      if (searchInput) searchInput.value = "";
      _wlSearchQuery = "";
      clearBtn.style.display = "none";
      if (_cachedScanData) applyWatchlistFiltering(_cachedScanData.watchlist || [], _cachedScanData);
    });
  }

  const sortSelect = document.getElementById("watchlistSortSelect");
  if (sortSelect) {
    sortSelect.addEventListener("change", () => {
      _wlSortMode = sortSelect.value;
      if (_cachedScanData) applyWatchlistFiltering(_cachedScanData.watchlist || [], _cachedScanData);
    });
  }

  document.querySelectorAll(".wl-filter-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".wl-filter-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      _wlSelectedFilter = chip.getAttribute("data-filter") || "all";
      if (_cachedScanData) applyWatchlistFiltering(_cachedScanData.watchlist || [], _cachedScanData);
    });
  });

  const resetBtn = document.getElementById("resetWatchlistFiltersBtn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      resetAllWatchlistFilters();
    });
  }
}

window.resetAllWatchlistFilters = function() {
  _wlSelectedFilter = "all";
  _wlSelectedSector = null;
  _wlSearchQuery = "";
  _wlSortMode = "score_desc";

  const searchInput = document.getElementById("watchlistSearchInput");
  if (searchInput) searchInput.value = "";
  const clearBtn = document.getElementById("clearWatchlistSearchBtn");
  if (clearBtn) clearBtn.style.display = "none";

  const sortSelect = document.getElementById("watchlistSortSelect");
  if (sortSelect) sortSelect.value = "score_desc";

  document.querySelectorAll(".wl-filter-chip").forEach(c => {
    if (c.getAttribute("data-filter") === "all") c.classList.add("active");
    else c.classList.remove("active");
  });

  if (_cachedScanData) {
    renderSectorLeadership(_cachedScanData.watchlist || []);
    applyWatchlistFiltering(_cachedScanData.watchlist || [], _cachedScanData);
  }
};

// =====================================================================
// EXPANDABLE WATCHLIST DETAIL PANEL & CANVAS MINI-CHART
// =====================================================================

// Extract known earnings if within next 7 days, else returns null
function extractEarningsDays(chartData, item) {
  if (item && item.earnings_in_days != null && item.earnings_in_days >= 0 && item.earnings_in_days <= 7) {
    return item.earnings_in_days;
  }
  const events = chartData?.chart?.result?.[0]?.events;
  if (events && events.earnings) {
    const nowSec = Date.now() / 1000;
    const sevenDaysSec = 7 * 86400;
    const earningsList = Object.values(events.earnings);
    for (const e of earningsList) {
      const eDate = e.date || e.startdate || e.timestamp;
      if (eDate && eDate >= nowSec && eDate <= nowSec + sevenDaysSec) {
        return Math.max(1, Math.ceil((eDate - nowSec) / 86400));
      }
    }
  }
  return null;
}

// Fetch 6-month chart data from Yahoo with localStorage cache keyed by symbol+date
async function fetchChartData(symbol) {
  const cleanSym = symbol.endsWith(".NS") ? symbol : `${symbol}.NS`;
  const today = new Date().toISOString().slice(0, 10);
  const cacheKey = `chart_${cleanSym}_${today}`;

  // Check localStorage cache first
  const cached = localStorage.getItem(cacheKey);
  if (cached) {
    try {
      return JSON.parse(cached);
    } catch (e) {
      localStorage.removeItem(cacheKey);
    }
  }

  const directUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${cleanSym}?interval=1d&range=6mo`;
  let data = null;

  try {
    const res = await fetch(directUrl);
    if (res.ok) {
      data = await res.json();
    }
  } catch (err) {
    console.warn("Direct Yahoo fetch failed, trying proxy fallback:", err);
  }

  // Graceful fallback proxies if direct fetch has CORS restriction in client browser
  if (!data || !data.chart || !data.chart.result) {
    const proxies = [
      `https://corsproxy.io/?url=${encodeURIComponent(directUrl)}`,
      `https://api.allorigins.win/raw?url=${encodeURIComponent(directUrl)}`
    ];
    for (const pUrl of proxies) {
      try {
        const res = await fetch(pUrl);
        if (res.ok) {
          data = await res.json();
          if (data && data.chart && data.chart.result) break;
        }
      } catch (e) {
        // try next
      }
    }
  }

  if (data && data.chart && data.chart.result && data.chart.result.length > 0) {
    try {
      localStorage.setItem(cacheKey, JSON.stringify(data));
    } catch (e) {
      console.warn("localStorage quota write notice:", e);
    }
    return data;
  }
  return null;
}

// Standard Wilder's RSI calculation helper
function calculateRSI(closes, period = 14) {
  if (!closes || closes.length <= period) return 50;
  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) gains += diff;
    else losses -= diff;
  }
  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) {
      avgGain = (avgGain * (period - 1) + diff) / period;
      avgLoss = (avgLoss * (period - 1)) / period;
    } else {
      avgGain = (avgGain * (period - 1)) / period;
      avgLoss = (avgLoss * (period - 1) - diff) / period;
    }
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

// Plain HTML5 Canvas Mini-Chart Renderer with SMA50, SMA200, Breakout Line, and Volume Subplot
function drawMiniChart(canvas, candles, breakoutLevel, symbol) {
  const container = canvas.parentElement;
  const width = Math.max(240, Math.floor(container.clientWidth || 800));
  const height = 280;
  const dpr = window.devicePixelRatio || 1;

  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = "100%";
  canvas.style.maxWidth = `${width}px`;
  canvas.style.height = `${height}px`;

  // Retain data reference for seamless redraw on window resize
  canvas._candles = candles;
  canvas._breakoutLevel = breakoutLevel;
  canvas._symbol = symbol;

  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);

  const n = candles.length;
  if (n === 0) return;

  const marginTop = 22;
  const priceHeight = 170;
  const priceBottom = marginTop + priceHeight;
  const volumeGap = 16;
  const volumeTop = priceBottom + volumeGap;
  const volumeHeight = 44;
  const volumeBottom = volumeTop + volumeHeight;
  const marginLeft = width < 420 ? 8 : 14;
  const marginRight = width < 420 ? 54 : 74;
  const plotWidth = Math.max(10, width - marginLeft - marginRight);

  const barStep = plotWidth / n;
  const barWidth = Math.max(1, Math.min(8, barStep * 0.68));

  // Determine min & max price bounds including breakout level
  let minPrice = Infinity;
  let maxPrice = -Infinity;
  for (const c of candles) {
    if (c.low < minPrice) minPrice = c.low;
    if (c.high > maxPrice) maxPrice = c.high;
  }
  if (breakoutLevel && !isNaN(breakoutLevel)) {
    minPrice = Math.min(minPrice, breakoutLevel);
    maxPrice = Math.max(maxPrice, breakoutLevel);
  }

  const priceRange = (maxPrice - minPrice) || 1;
  const pMin = minPrice - priceRange * 0.05;
  const pMax = maxPrice + priceRange * 0.05;
  const pSpan = pMax - pMin;

  function priceToY(p) {
    return priceBottom - ((p - pMin) / pSpan) * priceHeight;
  }

  // Calculate SMA 50 and SMA 200
  const sma50 = [];
  const sma200 = [];
  for (let i = 0; i < n; i++) {
    // SMA 50
    if (i >= 49) {
      let sum50 = 0;
      for (let j = i - 49; j <= i; j++) sum50 += candles[j].close;
      sma50.push(sum50 / 50);
    } else if (i >= 5) {
      let sumProg = 0;
      for (let j = 0; j <= i; j++) sumProg += candles[j].close;
      sma50.push(sumProg / (i + 1));
    } else {
      sma50.push(null);
    }

    // SMA 200 (uses full 200 if present or progressive rolling if in 6mo chart)
    if (i >= 199) {
      let sum200 = 0;
      for (let j = i - 199; j <= i; j++) sum200 += candles[j].close;
      sma200.push(sum200 / 200);
    } else if (i >= 15) {
      let sumProg = 0;
      for (let j = 0; j <= i; j++) sumProg += candles[j].close;
      sma200.push(sumProg / (i + 1));
    } else {
      sma200.push(null);
    }
  }

  // Max volume for volume subplot
  let maxVol = 0;
  for (const c of candles) {
    if (c.volume > maxVol) maxVol = c.volume;
  }
  maxVol = maxVol || 1;

  function volToH(v) {
    return Math.max(1, (v / maxVol) * volumeHeight);
  }

  // 1. Grid Lines & Price Ticks
  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#64748b";
  ctx.font = "10px Inter, sans-serif";
  ctx.textAlign = "left";

  const numGridTicks = 4;
  for (let t = 0; t <= numGridTicks; t++) {
    const p = pMin + (pSpan / numGridTicks) * t;
    const y = priceToY(p);
    ctx.beginPath();
    ctx.moveTo(marginLeft, y);
    ctx.lineTo(width - marginRight, y);
    ctx.stroke();
    ctx.fillText("₹" + p.toFixed(1), width - marginRight + 6, y + 3);
  }

  // Volume separator line & label
  ctx.beginPath();
  ctx.moveTo(marginLeft, volumeTop - 4);
  ctx.lineTo(width - marginRight, volumeTop - 4);
  ctx.stroke();
  ctx.fillText("Vol", width - marginRight + 6, volumeTop + 14);

  // 2. Volume Subplot Bars
  for (let i = 0; i < n; i++) {
    const c = candles[i];
    const x = marginLeft + i * barStep + barStep / 2;
    const h = volToH(c.volume);
    const y = volumeBottom - h;
    ctx.fillStyle = c.close >= c.open ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)";
    ctx.fillRect(x - barWidth / 2, y, barWidth, h);
  }

  // 3. Candlesticks (Price)
  for (let i = 0; i < n; i++) {
    const c = candles[i];
    const x = marginLeft + i * barStep + barStep / 2;
    const isGreen = c.close >= c.open;
    const color = isGreen ? "#10b981" : "#ef4444";

    // Wick line
    const highY = priceToY(c.high);
    const lowY = priceToY(c.low);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, highY);
    ctx.lineTo(x, lowY);
    ctx.stroke();

    // Body rectangle
    const openY = priceToY(c.open);
    const closeY = priceToY(c.close);
    const bodyTop = Math.min(openY, closeY);
    const bodyH = Math.max(1.5, Math.abs(closeY - openY));
    ctx.fillStyle = color;
    ctx.fillRect(x - barWidth / 2, bodyTop, barWidth, bodyH);
  }

  // 4. Overlay SMA 50 (Orange)
  ctx.strokeStyle = "#f97316";
  ctx.lineWidth = 2;
  ctx.beginPath();
  let sma50Started = false;
  for (let i = 0; i < n; i++) {
    if (sma50[i] != null) {
      const x = marginLeft + i * barStep + barStep / 2;
      const y = priceToY(sma50[i]);
      if (!sma50Started) {
        ctx.moveTo(x, y);
        sma50Started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
  }
  ctx.stroke();

  // 5. Overlay SMA 200 (Blue)
  ctx.strokeStyle = "#3b82f6";
  ctx.lineWidth = 2;
  ctx.beginPath();
  let sma200Started = false;
  for (let i = 0; i < n; i++) {
    if (sma200[i] != null) {
      const x = marginLeft + i * barStep + barStep / 2;
      const y = priceToY(sma200[i]);
      if (!sma200Started) {
        ctx.moveTo(x, y);
        sma200Started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
  }
  ctx.stroke();

  // 6. Horizontal Dashed Line at 20-Day Breakout Level
  if (breakoutLevel && !isNaN(breakoutLevel)) {
    const bY = priceToY(breakoutLevel);
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(marginLeft, bY);
    ctx.lineTo(width - marginRight, bY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Breakout text badge on right
    ctx.fillStyle = "#ef4444";
    ctx.font = "bold 10px Inter, sans-serif";
    ctx.fillText("Breakout", width - marginRight + 6, bY - 3);
    ctx.fillStyle = "#fca5a5";
    ctx.font = "9px Inter, sans-serif";
    ctx.fillText("₹" + breakoutLevel.toFixed(1), width - marginRight + 6, bY + 9);
  }

  // 7. Date Ticks on Bottom Axis
  ctx.fillStyle = "#64748b";
  ctx.font = "10px Inter, sans-serif";
  ctx.textAlign = "center";
  const dateStep = Math.max(1, Math.floor(n / 4));
  for (let i = 0; i < n; i += dateStep) {
    if (candles[i] && candles[i].time) {
      const d = new Date(candles[i].time * 1000);
      const str = d.toLocaleDateString("en-IN", { month: "short", day: "numeric" });
      const x = marginLeft + i * barStep + barStep / 2;
      ctx.fillText(str, x, height - 3);
    }
  }
}

// Toggle detail row below the clicked stock row
async function toggleWatchlistDetail(row, item, scanData) {
  const symbol = item.Symbol;
  const existingDetail = document.getElementById(`detail-${symbol}`);

  // If already open, collapse it with 0.3s smooth transition
  if (existingDetail) {
    const drawer = existingDetail.querySelector(".accordion-drawer");
    if (drawer) {
      drawer.classList.remove("open");
      setTimeout(() => {
        if (existingDetail.parentNode) existingDetail.remove();
      }, 300);
    } else {
      existingDetail.remove();
    }
    row.classList.remove("expanded");
    const chevron = row.querySelector(".chevron");
    if (chevron) chevron.textContent = "▼";
    return;
  }

  // Close other open detail rows to keep view tidy
  document.querySelectorAll(".detail-row").forEach(el => {
    const d = el.querySelector(".accordion-drawer");
    if (d) d.classList.remove("open");
    setTimeout(() => {
      if (el.parentNode) el.remove();
    }, 300);
  });
  document.querySelectorAll(".watchlist-row.expanded").forEach(el => {
    el.classList.remove("expanded");
    const ch = el.querySelector(".chevron");
    if (ch) ch.textContent = "▼";
  });

  row.classList.add("expanded");
  const chevron = row.querySelector(".chevron");
  if (chevron) chevron.textContent = "▲";

  // Initial checklist values
  const trendPass = item.Trend === "YES";
  const setupPass = item.Coiling === "YES";
  const secPass = item.SectorBullish === "YES";
  const mktPass = Boolean(scanData && scanData.market_ok);
  const volPassInit = item.VolDryup === "YES";
  const rsiPassInit = item.RsiInRange === "YES";

  // Trade Action Blueprint calculations (Item #4)
  const close = parseFloat(item.Close) || 0;
  const dist = parseFloat(item["DistToBreakout%"]) || 0;
  const breakoutLevel = item.Breakout ? parseFloat(item.Breakout) : (item.Entry ? parseFloat(item.Entry) : Number((close * (1 + dist / 100)).toFixed(2)));
  const atr = parseFloat(item.ATR14) || Number((close * 0.025).toFixed(2));
  const stopPrice = item.Stop ? parseFloat(item.Stop) : Number(Math.max(1, breakoutLevel - 1.5 * atr).toFixed(2));
  const riskAmt = Math.max(0.01, breakoutLevel - stopPrice);
  const riskPct = ((riskAmt / (breakoutLevel || 1)) * 100).toFixed(1);
  const targetPrice = item.Target ? parseFloat(item.Target) : Number((breakoutLevel + 2 * riskAmt).toFixed(2));
  const targetPct = (((targetPrice - breakoutLevel) / (breakoutLevel || 1)) * 100).toFixed(1);
  const bePrice = Number((breakoutLevel * 1.08).toFixed(2));
  const atrPct = ((atr / (close || 1)) * 100).toFixed(1);

  // SC-6: Relative Strength, Institutional Footprint, Base Maturity & Stage
  const rawRs = item.rs_rating != null ? Number(item.rs_rating) : (item.RS_RATING != null ? Number(item.RS_RATING) : null);
  let rsBadge = "";
  if (rawRs !== null && !isNaN(rawRs)) {
    const rsVal = Math.round(rawRs);
    let rsClass = "rs-pill-gray";
    if (rsVal >= 90) rsClass = "rs-pill-green";
    else if (rsVal >= 80) rsClass = "rs-pill-blue";
    rsBadge = `<span class="rs-pill ${rsClass}">RS ${rsVal}</span>`;
  } else {
    rsBadge = `<span class="rs-pill rs-pill-gray">RS n/a</span>`;
  }

  const instFp = item.inst_footprint || "unknown";
  let instBadge = "";
  if (instFp === "accumulation") {
    instBadge = `<span class="inst-pill inst-pill-acc">🏦 ACCUM</span>`;
  } else if (instFp === "churn") {
    instBadge = `<span class="inst-pill inst-pill-churn">⚠️ CHURN</span>`;
  } else {
    instBadge = `<span class="inst-pill inst-pill-unk">⚪ UNK</span>`;
  }

  const isCoiling = item.Coiling === "YES";
  const basePill = `<span class="pill ${isCoiling ? 'pill-success' : 'pill-warning'}">Stage 2 ${isCoiling ? 'Tight Coil (Mature)' : 'Consolidating'}</span>`;

  const detailHtml = `
    <tr class="accordion-drawer-row detail-row" id="detail-${symbol}">
      <td colspan="9">
        <div class="accordion-drawer stock-detail-panel" id="drawer-${symbol}">
          <div class="detail-header">
            <div class="detail-title-group">
              <span class="detail-symbol">${symbol}</span>
              <span class="badge badge-neutral">${item.Sector || "^NSEI"}</span>
              <span class="badge badge-success">₹${item.Close || 0}</span>
              <span class="badge badge-warning">${dist.toFixed(2)}% to Breakout</span>
              <button class="btn btn-sm btn-primary size-trade-btn" data-symbol="${symbol}">
                🎯 Size this trade
              </button>
              <button class="btn btn-sm btn-secondary tv-chart-trigger-btn" data-symbol="${symbol}" title="Open interactive TradingView chart">
                📊 Interactive Chart
              </button>
              <button class="btn btn-sm btn-secondary gtt-copy-btn"
                data-symbol="${symbol}"
                data-entry="${breakoutLevel}"
                data-stop="${stopPrice}"
                data-target="${targetPrice}"
                data-qty="10"
                title="Copy GTT Breakout & Stop order parameters for Zerodha Kite / Groww">
                📋 GTT
              </button>
              <span class="detail-hint">(Click row to collapse)</span>
            </div>
            <div id="earnings-warn-${symbol}"></div>
          </div>

          <!-- SC-6 Accordion Intelligence Strip: RS | Inst | Base Maturity -->
          <div class="accordion-grid">
            <div class="accordion-card">
              <div class="accordion-card-title">Relative Strength (RS)</div>
              <div style="display: flex; align-items: center; gap: 8px;">
                ${rsBadge}
                <span style="font-size: 12px; color: var(--text-dim);">${rawRs !== null ? `${Math.round(rawRs)}th percentile vs Nifty 500` : 'RS Index benchmark'}</span>
              </div>
            </div>
            <div class="accordion-card">
              <div class="accordion-card-title">Institutional Footprint</div>
              <div style="display: flex; align-items: center; gap: 8px;">
                ${instBadge}
                <span style="font-size: 12px; color: var(--text-dim);">${instFp === 'accumulation' ? 'Smart-money accumulation detected' : (instFp === 'churn' ? 'High volume / low delivery warning' : 'Normal retail / bulk volume')}</span>
              </div>
            </div>
            <div class="accordion-card">
              <div class="accordion-card-title">Base Maturity &amp; Stage</div>
              <div style="display: flex; align-items: center; gap: 8px;">
                ${basePill}
                <span style="font-size: 12px; color: var(--text-dim);">20D Range: ${isCoiling ? 'Tight Compression' : 'Developing'}</span>
              </div>
            </div>
          </div>

          <!-- SC-6 Trade Thesis Card -->
          <div class="card" style="margin-bottom: 16px; padding: 12px 16px; background: rgba(255, 255, 255, 0.02); border-left: 3px solid var(--primary); border-radius: 8px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
              <span style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-main);">💡 Trade Thesis &amp; Catalyst</span>
              <span class="pill ${dist <= 1.0 ? 'pill-success' : 'pill-primary'}">${dist <= 1.0 ? 'Ready for Trigger' : 'Resting GTT Setup'}</span>
            </div>
            <p style="font-size: 12.5px; color: var(--text-muted); margin: 0; line-height: 1.55;">
              ${escapeHtml(item.thesis || `${symbol} is in a confirmed Stage 2 uptrend with RS ${rawRs !== null ? Math.round(rawRs) : 'solid'} relative momentum in the ${item.Sector || 'Small-Cap'} sector. Price is coiling ${dist.toFixed(1)}% below the 20-day high trigger at ₹${breakoutLevel.toFixed(2)}. ${item.VolDryup === 'YES' ? 'Volume has dried up significantly below the 50-day average, signaling supply exhaustion.' : 'Monitoring for institutional breakout volume print.'}`)}
            </p>
          </div>

          <!-- Event Radar Timeline Strip (SC-4) -->
          <div class="event-timeline-strip" id="event-radar-${symbol}">
            <div class="event-timeline-header">
              <span>📡 <strong>Event Radar</strong></span>
              <span class="badge ${item.next_event && item.next_event.days_to_event <= 5 ? 'badge-danger' : (item.next_event ? 'badge-warning' : 'badge-success')}">
                ${item.next_event ? `${item.next_event.type} in ${item.next_event.days_to_event}d` : 'Clear Horizon'}
              </span>
            </div>
            <div style="font-size: 12px; color: var(--text-dim); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
              <span>${item.next_event ? (item.next_event.note || `Scheduled ${item.next_event.type} on ${item.next_event.date}`) : 'No imminent corporate actions (AGM/Lock-in/Record/Earnings) detected within 30 days.'}</span>
              ${item.next_event && item.next_event.days_to_event <= 5 ? '<span style="color: #f87171; font-weight: 700;">⚠️ ENTRY GATE ACTIVE: New buy signals blocked within 5d blackout</span>' : ''}
            </div>
          </div>

          <!-- Trade Execution Blueprint (Item #4) -->
          <div class="blueprint-card">
            <div class="blueprint-header">
              <div class="blueprint-title-group">
                <span style="font-size: 16px;">🎯</span>
                <span class="blueprint-title">Trade Action Blueprint</span>
                <span class="blueprint-rr-pill">Planned R:R = 1 : 2.0</span>
              </div>
              <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                <button class="btn btn-xs btn-outline-primary size-trade-btn" data-symbol="${symbol}" title="Size this trade with Position Sizer">
                  🎯 Size at 1% Risk
                </button>
                <button class="btn btn-xs btn-outline-secondary gtt-copy-btn"
                  data-symbol="${symbol}"
                  data-entry="${breakoutLevel}"
                  data-stop="${stopPrice}"
                  data-target="${targetPrice}"
                  data-qty="10"
                  title="Copy GTT Breakout & Stop order parameters for Zerodha Kite / Groww">
                  📋 Copy GTT
                </button>
              </div>
            </div>
            <div class="blueprint-grid">
              <div class="blueprint-item entry-box">
                <span class="bp-label">Breakout Trigger (Entry)</span>
                <span class="bp-val">₹${breakoutLevel.toFixed(2)}</span>
                <span class="bp-sub">20-day high (${dist.toFixed(1)}% away)</span>
              </div>
              <div class="blueprint-item stop-box">
                <span class="bp-label">Hard Stop-Loss (1.5× ATR)</span>
                <span class="bp-val danger">₹${stopPrice.toFixed(2)}</span>
                <span class="bp-sub danger">-${riskPct}% risk (₹${riskAmt.toFixed(2)}/sh)</span>
              </div>
              <div class="blueprint-item target-box">
                <span class="bp-label">Initial 2R Target</span>
                <span class="bp-val success">₹${targetPrice.toFixed(2)}</span>
                <span class="bp-sub success">+${targetPct}% gain (+2R multiple)</span>
              </div>
              <div class="blueprint-item be-box">
                <span class="bp-label">Breakeven Ratchet (+8%)</span>
                <span class="bp-val accent">₹${bePrice.toFixed(2)}</span>
                <span class="bp-sub accent">Move stop to entry on hit</span>
              </div>
              <div class="blueprint-item time-box">
                <span class="bp-label">Time Stop Rule</span>
                <span class="bp-val warning">Day 5 Session</span>
                <span class="bp-sub">Exit if gain is &lt; 3% on Day 5</span>
              </div>
              <div class="blueprint-item vol-box">
                <span class="bp-label">Daily Range (ATR 14)</span>
                <span class="bp-val">₹${atr.toFixed(2)}</span>
                <span class="bp-sub">${atrPct}% typical daily volatility</span>
              </div>
            </div>
          </div>

          <!-- Rules Checklist -->
          <div class="checklist-title">Setup Criteria Checklist</div>
          <div class="checklist-grid" id="checklist-${symbol}">
            <div class="check-item ${trendPass ? 'pass' : 'fail'}">
              <span class="check-icon">${trendPass ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Trend Filter</span>
                <span class="check-desc">Stage 2 Uptrend (Close > SMA50 > SMA200)</span>
              </div>
              <span class="check-status">${trendPass ? 'Passed (+25)' : 'Failed (0)'}</span>
            </div>

            <div class="check-item ${setupPass ? 'pass' : 'fail'}">
              <span class="check-icon">${setupPass ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Setup (Coiling)</span>
                <span class="check-desc">Vol contraction & range tightness</span>
              </div>
              <span class="check-status">${setupPass ? 'Passed (+15)' : 'Failed (0)'}</span>
            </div>

            <div class="check-item ${secPass ? 'pass' : 'fail'}">
              <span class="check-icon">${secPass ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Sector Bullish</span>
                <span class="check-desc">${item.Sector || '^NSEI'} active Stage 2 uptrend</span>
              </div>
              <span class="check-status">${secPass ? 'Passed (+15)' : 'Failed (0)'}</span>
            </div>

            <div class="check-item ${mktPass ? 'pass' : 'fail'}">
              <span class="check-icon">${mktPass ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Market OK (M-Rule)</span>
                <span class="check-desc">NIFTY 50 Benchmark Uptrend</span>
              </div>
              <span class="check-status">${mktPass ? 'Passed (+5)' : 'Failed (Capped ≤50)'}</span>
            </div>

            <div class="check-item ${volPassInit ? 'pass' : 'fail'}" id="vol-check-${symbol}">
              <span class="check-icon">${volPassInit ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Volume Dry-Up</span>
                <span class="check-desc">VOL5 < 80% of VOL50</span>
              </div>
              <span class="check-status">${volPassInit ? 'Passed (+10)' : 'Failed (0)'}</span>
            </div>

            <div class="check-item ${rsiPassInit ? 'pass' : 'fail'}" id="rsi-check-${symbol}">
              <span class="check-icon">${rsiPassInit ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">RSI In Range (40-65)</span>
                <span class="check-desc">Momentum healthy, not overbought</span>
              </div>
              <span class="check-status">${rsiPassInit ? 'Passed (+10)' : 'Failed (0)'}</span>
            </div>
          </div>

          <!-- Chart Section -->
          <div class="detail-chart-section">
            <div class="chart-top-bar">
              <div class="chart-title-legend">
                <span class="chart-heading">6-Month Daily Candles</span>
                <span class="legend-item"><span class="legend-dot sma50-dot"></span> SMA 50</span>
                <span class="legend-item"><span class="legend-dot sma200-dot"></span> SMA 200</span>
                <span class="legend-item"><span class="legend-line breakout-line"></span> 20D Breakout</span>
              </div>
              <div class="chart-meta-stats" id="chart-meta-${symbol}">Loading 6-month chart...</div>
            </div>
            <div class="canvas-wrapper" style="position: relative; width: 100%; height: 280px;">
              <canvas id="canvas-${symbol}" class="mini-chart-canvas"></canvas>
              <div id="chart-loader-${symbol}" class="chart-loading-overlay">
                <div class="spinner"></div>
                <span>Fetching 6-month daily data from Yahoo Finance...</span>
              </div>
            </div>
          </div>
        </div>
      </td>
    </tr>
  `;

  row.insertAdjacentHTML("afterend", detailHtml);

  // Trigger smooth 0.3s accordion open transition
  requestAnimationFrame(() => {
    const drawer = document.getElementById(`drawer-${symbol}`);
    if (drawer) drawer.classList.add("open");
  });

  // Attach listener to all "Size this trade" buttons inside the detail panel
  const detailEl = document.getElementById(`detail-${symbol}`);
  if (detailEl) {
    detailEl.querySelectorAll(".size-trade-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        openPositionSizerFor(item);
      });
    });
  }

  // Default breakout level from item
  const distPct = parseFloat(item["DistToBreakout%"]) || 0;
  const initialBreakout = item.Close ? item.Close * (1 + distPct / 100) : null;

  try {
    const chartData = await fetchChartData(symbol);
    const canvas = document.getElementById(`canvas-${symbol}`);
    const loader = document.getElementById(`chart-loader-${symbol}`);
    const metaEl = document.getElementById(`chart-meta-${symbol}`);
    const warnEl = document.getElementById(`earnings-warn-${symbol}`);

    if (!canvas) return; // closed before fetch resolved

    if (loader) loader.style.display = "none";

    if (!chartData || !chartData.chart || !chartData.chart.result || chartData.chart.result.length === 0) {
      if (metaEl) metaEl.textContent = "Chart unavailable (Yahoo API rate limit or network error)";
      return;
    }

    const res = chartData.chart.result[0];
    const timestamps = res.timestamp || [];
    const quote = res.indicators?.quote?.[0] || {};
    const candles = [];

    for (let i = 0; i < timestamps.length; i++) {
      const o = quote.open?.[i];
      const h = quote.high?.[i];
      const l = quote.low?.[i];
      const c = quote.close?.[i];
      const v = quote.volume?.[i] || 0;
      if (o != null && h != null && l != null && c != null && !isNaN(c)) {
        candles.push({ time: timestamps[i], open: o, high: h, low: l, close: c, volume: v });
      }
    }

    if (candles.length === 0) {
      if (metaEl) metaEl.textContent = "No valid trading candles returned.";
      return;
    }

    // Determine 20D breakout level from candles if available
    const last20 = candles.slice(-21, -1);
    const calculatedBreakout = last20.length > 0 ? Math.max(...last20.map(c => c.high)) : initialBreakout;
    const finalBreakout = calculatedBreakout || initialBreakout;

    // Check earnings within next 7 days
    const earningsDays = extractEarningsDays(chartData, item);
    if (earningsDays !== null && warnEl) {
      warnEl.innerHTML = `<div class="earnings-warning-banner">⚠️ Earnings in ${earningsDays} day${earningsDays === 1 ? '' : 's'}</div>`;
    }

    // Live validation for VolDryup / RsiInRange if not pre-populated
    if (item.VolDryup === undefined && candles.length >= 50) {
      const vol5 = candles.slice(-5).reduce((s, c) => s + c.volume, 0) / 5;
      const vol50 = candles.slice(-50).reduce((s, c) => s + c.volume, 0) / 50;
      const volPass = vol5 < 0.8 * vol50;
      const el = document.getElementById(`vol-check-${symbol}`);
      if (el) {
        el.className = `check-item ${volPass ? 'pass' : 'fail'}`;
        el.querySelector(".check-icon").textContent = volPass ? '✅' : '❌';
        el.querySelector(".check-status").textContent = volPass ? 'Passed (+10)' : 'Failed (0)';
      }
    }

    if (item.RsiInRange === undefined && candles.length >= 15) {
      const closes = candles.map(c => c.close);
      const rsi = calculateRSI(closes, 14);
      const rsiPass = rsi >= 40 && rsi <= 65;
      const el = document.getElementById(`rsi-check-${symbol}`);
      if (el) {
        el.className = `check-item ${rsiPass ? 'pass' : 'fail'}`;
        el.querySelector(".check-icon").textContent = rsiPass ? '✅' : '❌';
        el.querySelector(".check-status").textContent = rsiPass ? `Passed (RSI ${rsi.toFixed(1)})` : `Failed (RSI ${rsi.toFixed(1)})`;
      }
    }

    // Draw the chart on HTML5 canvas
    drawMiniChart(canvas, candles, finalBreakout, symbol);

    if (metaEl) {
      const lastCandle = candles[candles.length - 1];
      metaEl.textContent = `${candles.length} trading days • Close: ₹${lastCandle.close.toFixed(2)} • 20D Breakout: ₹${finalBreakout.toFixed(2)}`;
    }
  } catch (err) {
    console.error("Error loading mini chart:", err);
    const metaEl = document.getElementById(`chart-meta-${symbol}`);
    if (metaEl) metaEl.textContent = "Error rendering chart: " + err.message;
  }
}

// Redraw open detail canvases on window resize (debounced)
let _resizeCanvasTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(_resizeCanvasTimer);
  _resizeCanvasTimer = setTimeout(() => {
    document.querySelectorAll(".detail-row").forEach(detailRow => {
      const canvas = detailRow.querySelector("canvas");
      if (canvas && canvas._candles) {
        drawMiniChart(canvas, canvas._candles, canvas._breakoutLevel, canvas._symbol);
      }
    });
  }, 100);
});

// =====================================================================
// POSITION SIZER & RISK CALCULATOR
// =====================================================================

// Open and pre-fill Position Sizer from a Watchlist row
function openPositionSizerFor(item) {
  if (!item) return;

  // 1. Switch tab to Open Positions
  const openTabBtn = document.querySelector('.tab-btn[data-tab="tabOpen"]');
  if (openTabBtn) {
    openTabBtn.click();
  }

  // 2. Pre-fill Entry with the stock's close and Stop with close minus 1.5 times ATR (or signal stop when available)
  const symbol = item.Symbol || "";
  const close = parseFloat(item.Close) || (item.Entry ? parseFloat(item.Entry) : 0);
  const entryPrice = close > 0 ? Number(close.toFixed(2)) : 0;

  let stopPrice = 0;
  if (item.Stop && !isNaN(item.Stop)) {
    stopPrice = Number(parseFloat(item.Stop).toFixed(2));
  } else if (close > 0) {
    const atrVal = parseFloat(item.ATR14 || item.ATR || 0);
    if (atrVal > 0) {
      stopPrice = Number((close - 1.5 * atrVal).toFixed(2));
    } else {
      stopPrice = Number((close * 0.95).toFixed(2));
    }
  }

  const symInput = document.getElementById("sizerSymbol");
  const entryInput = document.getElementById("sizerEntry");
  const stopInput = document.getElementById("sizerStop");

  if (symInput) symInput.value = symbol;
  if (entryInput) entryInput.value = entryPrice > 0 ? entryPrice : "";
  if (stopInput) stopInput.value = stopPrice > 0 ? stopPrice : "";

  // Auto-calculate outputs
  updatePositionSizer();

  // 3. Highlight and smooth scroll into view
  const card = document.getElementById("positionSizerCard");
  if (card) {
    card.scrollIntoView({ behavior: "smooth", block: "start" });
    card.classList.add("highlight-flash");
    setTimeout(() => card.classList.remove("highlight-flash"), 1500);
  }
}

// Auto-compute Position Sizer metrics & /buy command
function updatePositionSizer() {
  const symbolInput = document.getElementById("sizerSymbol");
  const capitalInput = document.getElementById("sizerCapital");
  const riskPctInput = document.getElementById("sizerRiskPct");
  const entryInput = document.getElementById("sizerEntry");
  const stopInput = document.getElementById("sizerStop");

  if (!capitalInput) return; // not mounted

  const symbol = (symbolInput?.value || "").trim().toUpperCase();
  const capital = parseFloat(capitalInput.value) || 0;
  const riskPct = parseFloat(riskPctInput.value) || 0;
  const entry = parseFloat(entryInput?.value) || 0;
  const stop = parseFloat(stopInput?.value) || 0;

  const riskPerUnitEl = document.getElementById("sizerRiskPerUnit");
  const qtyEl = document.getElementById("sizerQty");
  const maxLossEl = document.getElementById("sizerMaxLoss");
  const targetEl = document.getElementById("sizerTarget");
  const exposureEl = document.getElementById("sizerExposure");
  const cmdPreviewEl = document.getElementById("sizerCmdPreview");
  const errorEl = document.getElementById("sizerError");

  if (entry <= 0 || stop <= 0) {
    if (riskPerUnitEl) riskPerUnitEl.textContent = "₹0.00";
    if (qtyEl) qtyEl.textContent = "0 units";
    if (maxLossEl) maxLossEl.textContent = "₹0.00";
    if (targetEl) targetEl.textContent = "₹0.00";
    if (exposureEl) exposureEl.textContent = "₹0.00";
    if (cmdPreviewEl) cmdPreviewEl.textContent = `/buy ${symbol || "SYMBOL"} ${entry || 0} 0 ${stop || 0} 0`;
    if (errorEl) errorEl.style.display = "none";
    return;
  }

  if (stop >= entry) {
    if (riskPerUnitEl) riskPerUnitEl.textContent = "Invalid";
    if (qtyEl) qtyEl.textContent = "0 units";
    if (maxLossEl) maxLossEl.textContent = "₹0.00";
    if (targetEl) targetEl.textContent = "₹0.00";
    if (exposureEl) exposureEl.textContent = "₹0.00";
    if (errorEl) {
      errorEl.textContent = "⚠️ Stop Loss must be lower than Entry Price for a swing trade.";
      errorEl.style.display = "block";
    }
    if (cmdPreviewEl) cmdPreviewEl.textContent = `/buy ${symbol || "SYMBOL"} ${entry} 0 ${stop} 0`;
    return;
  }

  if (errorEl) errorEl.style.display = "none";

  const riskPerUnit = entry - stop;
  const maxRiskBudget = capital * (riskPct / 100);
  const suggestedQty = Math.floor(maxRiskBudget / riskPerUnit);
  const maxLoss = suggestedQty * riskPerUnit;
  const target = entry + (2 * riskPerUnit);
  const totalExposure = suggestedQty * entry;

  if (riskPerUnitEl) riskPerUnitEl.textContent = formatINR(riskPerUnit);
  if (qtyEl) qtyEl.textContent = `${suggestedQty} unit${suggestedQty === 1 ? "" : "s"}`;
  if (maxLossEl) maxLossEl.textContent = formatINR(maxLoss);
  if (targetEl) targetEl.textContent = formatINR(target);
  if (exposureEl) exposureEl.textContent = formatINR(totalExposure);

  const cleanEntry = Number(entry.toFixed(2));
  const cleanStop = Number(stop.toFixed(2));
  const cleanTarget = Number(target.toFixed(2));

  const cmdString = `/buy ${symbol || "SYMBOL"} ${cleanEntry} ${suggestedQty} ${cleanStop} ${cleanTarget}`;
  if (cmdPreviewEl) cmdPreviewEl.textContent = cmdString;
}

// Copy /buy command string to clipboard and show toast
async function copyBuyCommand() {
  const cmdPreviewEl = document.getElementById("sizerCmdPreview");
  const cmd = cmdPreviewEl ? cmdPreviewEl.textContent.trim() : "";
  if (!cmd) return;

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(cmd);
    } else {
      const ta = document.createElement("textarea");
      ta.value = cmd;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    showToast("Copied - paste in Telegram");
  } catch (err) {
    try {
      const ta = document.createElement("textarea");
      ta.value = cmd;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      showToast("Copied - paste in Telegram");
    } catch (e2) {
      showToast("Copied - paste in Telegram");
    }
  }
}

// Toast notification helper
function showToast(message) {
  let toastContainer = document.getElementById("toastContainer");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "toastContainer";
    toastContainer.className = "toast-container";
    document.body.appendChild(toastContainer);
  }

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<span style="font-size: 16px;">📋</span> <span>${message}</span>`;
  toastContainer.appendChild(toast);

  setTimeout(() => toast.classList.add("show"), 10);

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

// Initialize Position Sizer listeners & initial state
function initPositionSizer() {
  const capitalInput = document.getElementById("sizerCapital");
  const riskPctInput = document.getElementById("sizerRiskPct");
  const entryInput = document.getElementById("sizerEntry");
  const stopInput = document.getElementById("sizerStop");
  const symbolInput = document.getElementById("sizerSymbol");
  const resetBtn = document.getElementById("sizerResetBtn");
  const copyBtn = document.getElementById("copyBuyCmdBtn");

  if (!capitalInput) return;

  const inputs = [capitalInput, riskPctInput, entryInput, stopInput, symbolInput];
  inputs.forEach(inp => {
    if (inp) {
      inp.addEventListener("input", updatePositionSizer);
      inp.addEventListener("change", updatePositionSizer);
    }
  });

  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      capitalInput.value = "100000";
      riskPctInput.value = "1";
      if (entryInput) entryInput.value = "";
      if (stopInput) stopInput.value = "";
      if (symbolInput) symbolInput.value = "";
      updatePositionSizer();
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", copyBuyCommand);
  }

  updatePositionSizer();
}

// 2. Render Tab: Open Positions
async function renderOpenPositions(positions) {
  const countBadge = document.getElementById("openCountBadge");
  const countCard = document.getElementById("openPositionsCount");
  const totalPnlCard = document.getElementById("openTotalPnl");
  const capitalCard = document.getElementById("openCapitalDeployed");
  const heatCard = document.getElementById("openPortfolioHeat");
  const heatSub = document.getElementById("openPortfolioHeatSub");
  const sectorAlert = document.getElementById("openPositionsSectorAlert");
  const tableBody = document.getElementById("openPositionsBody");

  if (!positions || positions.length === 0) {
    if (countBadge) countBadge.textContent = "0";
    if (countCard) countCard.textContent = "0";
    if (totalPnlCard) {
      totalPnlCard.textContent = "₹0.00";
      totalPnlCard.className = "stat-value neutral";
    }
    if (capitalCard) capitalCard.textContent = "₹0.00";
    if (heatCard) {
      heatCard.textContent = "0.0%";
      heatCard.className = "stat-value positive";
    }
    if (heatSub) heatSub.textContent = "₹0 at risk (0 open positions)";
    if (sectorAlert) sectorAlert.style.display = "none";
    if (tableBody) {
      tableBody.innerHTML = `
        <tr><td colspan="12" class="empty-state">💼 No active open positions recorded. Use /buy in Telegram to log trades.</td></tr>
      `;
    }
    return;
  }

  if (countBadge) countBadge.textContent = positions.length;
  if (countCard) countCard.textContent = positions.length;

  let totalUnrealized = 0;
  let totalCapital = 0;
  let totalRiskAmount = 0;
  const rows = [];

  for (const pos of positions) {
    const entry = parseFloat(pos.entry_price) || 0;
    const qty = parseInt(pos.qty, 10) || 0;
    const stop = pos.stop ? parseFloat(pos.stop) : null;
    const target = pos.target ? parseFloat(pos.target) : null;
    totalCapital += (entry * qty);

    // Fetch live price or fallback
    const livePrice = await fetchLivePrice(pos.symbol);
    const currentPrice = livePrice !== null ? livePrice : entry;
    const isLive = livePrice !== null;

    const unrealized = (currentPrice - entry) * qty;
    totalUnrealized += unrealized;

    let distToStopStr = "N/A";
    let distToTargetStr = "N/A";
    let isNearStop = false;
    let isNearTarget = false;

    if (stop && currentPrice > 0) {
      const pctToStop = ((currentPrice - stop) / currentPrice) * 100;
      distToStopStr = `${pctToStop.toFixed(1)}%`;
      if (pctToStop <= 2.0 && pctToStop >= -1.0) isNearStop = true;
    }

    if (target && currentPrice > 0) {
      const pctToTarget = ((target - currentPrice) / currentPrice) * 100;
      distToTargetStr = `${pctToTarget.toFixed(1)}%`;
      if (pctToTarget <= 2.0 && pctToTarget >= -1.0) isNearTarget = true;
    }

    // Attach computed live values for Today's Plan generator
    pos._live_price = currentPrice;
    pos._is_near_stop = isNearStop;
    pos._is_near_target = isNearTarget;

    // R-Multiple Trajectory & Progress calculations (Item #5)
    const plannedRiskPerUnit = (stop && entry > stop) ? (entry - stop) : (entry * 0.05);
    const posRiskAmount = plannedRiskPerUnit * qty;
    totalRiskAmount += posRiskAmount;

    const currentR = plannedRiskPerUnit > 0 ? (currentPrice - entry) / plannedRiskPerUnit : 0;
    const pctGainFromEntry = entry > 0 ? ((currentPrice - entry) / entry) * 100 : 0;
    const isBreakevenReached = pctGainFromEntry >= 8.0;

    // Gauge needle position: -1R = 0%, 0R = 33.3%, +1R = 66.7%, +2R = 100%
    const needlePercent = Math.max(0, Math.min(100, ((currentR + 1) / 3) * 100));

    let rPillClass = "r-neutral";
    let rPillText = `${currentR >= 0 ? "+" : ""}${currentR.toFixed(2)}R`;
    if (isBreakevenReached) {
      rPillClass = "r-breakeven";
      rPillText = `🎯 Ratchet BE (${currentR >= 0 ? "+" : ""}${currentR.toFixed(1)}R)`;
    } else if (currentR >= 1.8) {
      rPillClass = "r-target";
      rPillText = `🏆 Target Hit (${currentR.toFixed(1)}R)`;
    } else if (currentR > 0) {
      rPillClass = "r-profit";
    } else if (currentR <= -0.8) {
      rPillClass = "r-stop";
      rPillText = `⚠️ Defend Stop (${currentR.toFixed(2)}R)`;
    }

    const trajectoryHtml = `
      <div class="r-trajectory-cell">
        <div class="r-trajectory-header">
          <span class="r-pill ${rPillClass}">${rPillText}</span>
          <span class="r-gain-text ${unrealized >= 0 ? 'text-success' : 'text-danger'}">${unrealized >= 0 ? '+' : ''}${pctGainFromEntry.toFixed(1)}%</span>
        </div>
        <div class="r-gauge-track" title="Stop (-1R) → Entry (0R) → Target (+2R). Current: ${currentR.toFixed(2)}R">
          <div class="r-gauge-stop-zone"></div>
          <div class="r-gauge-entry-mark" title="Entry (0R)"></div>
          <div class="r-gauge-needle" style="left: ${needlePercent}%;"></div>
        </div>
        <div class="r-gauge-labels">
          <span>-1R</span>
          <span>Entry</span>
          <span>+2R</span>
        </div>
      </div>
    `;

    let rowClass = "";
    if (isNearStop) rowClass = "row-danger";
    else if (isNearTarget) rowClass = "row-green";

    const pnlSign = unrealized >= 0 ? "+" : "";
    const pnlClass = unrealized > 0 ? "style='color: var(--success); font-weight:600;'" : unrealized < 0 ? "style='color: var(--danger); font-weight:600;'" : "";

    // Event Radar Chip on Open Position (SC-4)
    let posEventChip = "";
    const posNextEv = pos.next_event || (_cachedScanData?.landmines?.find(l => l.symbol === pos.symbol));
    if (pos.warn_event || (posNextEv && posNextEv.days_to_event != null && posNextEv.days_to_event <= 3)) {
      const evType = escapeHtml(posNextEv?.type || "EVENT");
      const evDays = posNextEv?.days_to_event != null ? posNextEv.days_to_event : "≤3";
      posEventChip = `<span class="badge badge-warning warn-event-chip" style="margin-left: 6px; font-size: 10px;" title="🔔 Imminent Event: ${evType} in ${evDays}d - review hold">🔔 ${evType} ${evDays}d</span>`;
    }

    rows.push(`
      <tr class="${rowClass}">
        <td data-label="Symbol"><strong>${pos.symbol}</strong>${posEventChip}</td>
        <td data-label="Entry Date">${formatDate(pos.entry_date)}</td>
        <td data-label="Entry Price">${formatINR(entry)}</td>
        <td data-label="Qty">${qty}</td>
        <td data-label="Stop" style="color: var(--danger);">${stop ? formatINR(stop) : "None"}</td>
        <td data-label="Target" style="color: var(--success);">${target ? formatINR(target) : "None"}</td>
        <td data-label="Last Price">${formatINR(currentPrice)} ${!isLive ? "<small style='color: var(--text-dim);'>(entry)</small>" : ""}</td>
        <td data-label="Unrealized PnL" ${pnlClass}>${pnlSign}${formatINR(unrealized)}</td>
        <td data-label="% to Stop">${distToStopStr}</td>
        <td data-label="% to Target">${distToTargetStr}</td>
        <td data-label="R-Trajectory">${trajectoryHtml}</td>
        <td data-label="Action">
          <div style="display: flex; gap: 4px; align-items: center; justify-content: flex-end; flex-wrap: nowrap;">
            <button class="btn btn-xs btn-outline-primary tv-chart-trigger-btn" data-symbol="${pos.symbol}" title="Open TradingView Chart">
              📊 Chart
            </button>
            <button class="btn btn-xs btn-outline-secondary gtt-copy-btn"
              data-symbol="${pos.symbol}"
              data-entry="${entry}"
              data-stop="${stop}"
              data-target="${target}"
              data-qty="${qty}"
              title="Copy Zerodha/Groww GTT Stop & Target order snippet">
              📋 GTT
            </button>
          </div>
        </td>
      </tr>
    `);
  }

  // Update Summary Cards
  if (capitalCard) capitalCard.textContent = formatINR(totalCapital);
  if (totalPnlCard) {
    totalPnlCard.textContent = formatINR(totalUnrealized, true);
    totalPnlCard.className = `stat-value ${totalUnrealized > 0 ? "positive" : totalUnrealized < 0 ? "negative" : "neutral"}`;
  }

  // Portfolio Heat Card (Item #6)
  if (heatCard) {
    const accountCapital = 100000;
    const heatPct = ((totalRiskAmount / accountCapital) * 100).toFixed(1);
    heatCard.textContent = `${heatPct}%`;
    let heatClass = "positive";
    if (heatPct > 5.0) heatClass = "negative";
    else if (heatPct > 3.5) heatClass = "neutral";
    heatCard.className = `stat-value ${heatClass}`;

    if (heatSub) {
      heatSub.textContent = `₹${formatINR(totalRiskAmount)} at risk across ${positions.length} trade${positions.length === 1 ? '' : 's'}`;
    }
  }

  // Sector Concentration Warning (Item #6)
  if (sectorAlert) {
    const sectorCount = {};
    for (const pos of positions) {
      let sec = "Small Cap";
      if (_cachedScanData && _cachedScanData.watchlist) {
        const match = _cachedScanData.watchlist.find(w => w.Symbol === pos.symbol);
        if (match && match.Sector) sec = match.Sector;
      }
      sectorCount[sec] = (sectorCount[sec] || 0) + 1;
    }
    const multiSectors = Object.keys(sectorCount).filter(s => sectorCount[s] > 1);
    if (multiSectors.length > 0) {
      sectorAlert.innerHTML = `
        <span class="alert-icon">⚠️</span>
        <div class="alert-text">
          <strong>Sector Exposure Alert:</strong> ${multiSectors.map(s => `${sectorCount[s]} open positions in <strong>${escapeHtml(s)}</strong>`).join(", ")}. Sector risk cap reached; avoid taking new breakout entries in these sectors.
        </div>
      `;
      sectorAlert.className = "positions-alert-banner warning";
      sectorAlert.style.display = "flex";
    } else if (positions.length > 1) {
      sectorAlert.innerHTML = `
        <span class="alert-icon">🟢</span>
        <div class="alert-text">
          <strong>Sector Diversification Healthy:</strong> All ${positions.length} open positions belong to distinct industry sectors.
        </div>
      `;
      sectorAlert.className = "positions-alert-banner success";
      sectorAlert.style.display = "flex";
    } else {
      sectorAlert.style.display = "none";
    }
  }

  // Event Radar Imminent Warning / Discipline Card (SC-4)
  const eventAlert = document.getElementById("openPositionsEventAlert");
  if (eventAlert) {
    const imminentPositions = positions.filter(pos => {
      if (pos.warn_event) return true;
      if (pos.next_event && pos.next_event.days_to_event != null && pos.next_event.days_to_event <= 3) return true;
      if (_cachedScanData && _cachedScanData.landmines) {
        const lm = _cachedScanData.landmines.find(l => l.symbol === pos.symbol && l.days_to_event <= 3);
        if (lm) return true;
      }
      return false;
    });

    if (imminentPositions.length > 0) {
      eventAlert.innerHTML = `
        <span class="alert-icon" style="font-size: 18px;">🔔</span>
        <div class="alert-text">
          <strong>⚠️ Discipline Event Radar Warning:</strong> ${imminentPositions.map(p => {
            const ev = p.next_event || (_cachedScanData?.landmines?.find(l => l.symbol === p.symbol)) || { type: "EVENT", days_to_event: "≤3" };
            return `<strong>${escapeHtml(p.symbol)}</strong> (${escapeHtml(ev.type)} in ${ev.days_to_event}d)`;
          }).join(", ")}. Review hold before binary event (Stop-loss &amp; 2R Target remain untouched).
        </div>
      `;
      eventAlert.style.display = "flex";
    } else {
      eventAlert.style.display = "none";
    }
  }

  tableBody.innerHTML = rows.join("");

  // Update Today's Plan with live open positions metrics
  _cachedOpenPositions = positions;
  if (_cachedScanData) {
    renderTodaysPlan(_cachedScanData, _cachedOpenPositions);
  }
}

// 3. Render Tab: Trade History & Equity Curve
function renderHistory(trades) {
  const tableBody = document.getElementById("tradesBody");
  const totalBadge = document.getElementById("equityTotalBadge");

  if (!trades || trades.length === 0) {
    totalBadge.textContent = "₹0.00";
    totalBadge.className = "badge badge-neutral";
    tableBody.innerHTML = `
      <tr><td colspan="11" class="empty-state">📜 No closed trades recorded yet.</td></tr>
    `;
    const canvas = document.getElementById("equityChart");
    if (canvas && window.Chart) {
      if (equityChartInstance) {
        equityChartInstance.destroy();
      }
      const ctx = canvas.getContext("2d");
      equityChartInstance = new Chart(ctx, {
        type: "line",
        data: {
          labels: ["Baseline", "Current"],
          datasets: [{
            label: "Cumulative Realized PnL (₹)",
            data: [0, 0],
            borderColor: "#64748b",
            borderWidth: 2,
            pointRadius: 3,
            backgroundColor: "rgba(100, 116, 139, 0.08)",
            fill: true,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: "rgba(255, 255, 255, 0.04)" }, ticks: { color: "#94a3b8" } },
            y: { min: -100, max: 100, grid: { color: "rgba(255, 255, 255, 0.06)" }, ticks: { color: "#94a3b8", callback: (val) => formatINR(val) } }
          }
        }
      });
    }
    return;
  }

  // Sort trades newest first for the table
  const sortedTrades = [...trades].reverse();

  tableBody.innerHTML = sortedTrades.map(t => {
    const pnl = parseFloat(t.pnl) || 0;
    const pnlPct = parseFloat(t.pnl_pct) || 0;
    const sign = pnl >= 0 ? "+" : "";
    const colorStyle = pnl > 0 ? "style='color: var(--success); font-weight: 600;'" : "style='color: var(--danger); font-weight: 600;'";
    const rMultipleStr = t.r_multiple !== null && t.r_multiple !== undefined ? `${t.r_multiple > 0 ? "+" : ""}${t.r_multiple}R` : "N/A";

    const hasMistake = Boolean(t.mistake);
    const rowClass = hasMistake ? "trade-row row-mistake" : "trade-row";

    let mistakeBadge = "";
    if (t.mistake === "stop_moved") {
      mistakeBadge = `<div style="margin-top: 3px;"><span class="badge badge-danger term-lookup" data-term="Stop moved" style="font-size: 10px;" title="Discipline mistake: Exit price was worse than planned stop">⚠️ Stop Moved</span></div>`;
    } else if (t.mistake === "time_stop_ignored") {
      mistakeBadge = `<div style="margin-top: 3px;"><span class="badge badge-danger term-lookup" data-term="Time stop ignored" style="font-size: 10px;" title="Discipline mistake: Held > 5 days with return < 3%">⚠️ Time Stop Ignored</span></div>`;
    } else if (t.mistake) {
      mistakeBadge = `<div style="margin-top: 3px;"><span class="badge badge-danger" style="font-size: 10px;" title="Discipline mistake: ${escapeHtml(String(t.mistake))}">⚠️ ${escapeHtml(String(t.mistake))}</span></div>`;
    }

    // Merge system tags with user local post-mortem tags
    const localPm = getTradePostMortem(t.symbol, t.entry_date) || { tags: [], notes: "" };
    const rawTags = [...(Array.isArray(t.tags) ? t.tags : []), ...(localPm.tags || [])];
    const uniqueTags = [...new Set(rawTags.map(tag => String(tag).trim()))].filter(Boolean);

    let tagsHtml = `<span style="color: var(--text-dim); font-size: 11px;">-</span>`;
    if (uniqueTags.length > 0) {
      tagsHtml = uniqueTags.map(tag => {
        const clean = String(tag).trim().toLowerCase();
        let tagClass = "tag-default";
        if (clean === "#breakout" || clean === "#cleanbreakout") tagClass = "tag-breakout";
        else if (clean === "#pullback") tagClass = "tag-pullback";
        else if (clean === "#plan_followed" || clean === "#followedplan" || clean === "#targethit") tagClass = "tag-plan";
        else if (clean === "#fomo" || clean === "#chasedgap" || clean === "#stopmoved" || clean === "#revengetrade") tagClass = "tag-fomo";
        return `<span class="tag-pill ${tagClass}">${escapeHtml(String(tag))}</span>`;
      }).join("");
    }

    const noteText = t.note || "";
    const reflectionText = localPm.notes || "";
    let noteCellHtml = "";
    if (reflectionText) {
      noteCellHtml = `
        <div class="trade-note-block">
          ${noteText ? `<div class="trade-system-note"><small>${escapeHtml(noteText)}</small></div>` : ""}
          <div class="trade-pm-reflection"><span class="pm-reflection-icon">📝</span> <em>"${escapeHtml(reflectionText)}"</em></div>
        </div>
      `;
    } else {
      noteCellHtml = `<small style="color: var(--text-muted);">${escapeHtml(noteText || "-")}</small>`;
    }

    return `
      <tr class="${rowClass}">
        <td data-label="Symbol">
          <strong>${escapeHtml(t.symbol || "")}</strong>
          ${mistakeBadge}
        </td>
        <td data-label="Tags">${tagsHtml}</td>
        <td data-label="Entry Date">${formatDate(t.entry_date)}</td>
        <td data-label="Entry">${formatINR(t.entry_price)}</td>
        <td data-label="Qty">${t.qty || 0}</td>
        <td data-label="Exit Date">${formatDate(t.exit_date)}</td>
        <td data-label="Exit">${formatINR(t.exit_price)}</td>
        <td data-label="Realized PnL" ${colorStyle}>${sign}${formatINR(pnl)}</td>
        <td data-label="Return %" ${colorStyle}>${sign}${pnlPct.toFixed(2)}%</td>
        <td data-label="R-Multiple"><span class="badge ${pnl > 0 ? "badge-success" : "badge-danger"}">${rMultipleStr}</span></td>
        <td data-label="Note & Reflection">${noteCellHtml}</td>
        <td data-label="Action">
          <button class="btn btn-xs btn-outline-secondary pm-edit-btn"
            data-symbol="${escapeHtml(t.symbol || '')}"
            data-entry-date="${escapeHtml(t.entry_date || '')}"
            data-exit-date="${escapeHtml(t.exit_date || '')}"
            data-entry-price="${t.entry_price || 0}"
            data-exit-price="${t.exit_price || 0}"
            data-pnl="${pnl}"
            data-r="${t.r_multiple !== null && t.r_multiple !== undefined ? t.r_multiple : 'N/A'}"
            title="Add post-mortem takeaways & execution tags">
            📝 Reflect
          </button>
        </td>
      </tr>
    `;
  }).join("");

  // Calculate Cumulative Equity Curve in chronological order
  const labels = ["Start"];
  const equityPoints = [0];
  let runningPnl = 0;

  for (let i = 0; i < trades.length; i++) {
    const t = trades[i];
    runningPnl += (parseFloat(t.pnl) || 0);
    labels.push(`${t.symbol} (#${i + 1})`);
    equityPoints.push(runningPnl);
  }

  totalBadge.textContent = formatINR(runningPnl, true);
  totalBadge.className = `badge ${runningPnl >= 0 ? "badge-success" : "badge-danger"}`;

  // Render Chart via Chart.js
  const canvas = document.getElementById("equityChart");
  if (canvas && window.Chart) {
    if (equityChartInstance) {
      equityChartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, runningPnl >= 0 ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)");
    gradient.addColorStop(1, "rgba(15, 23, 42, 0.0)");

    equityChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Cumulative Realized PnL (₹)",
          data: equityPoints,
          borderColor: runningPnl >= 0 ? "#10b981" : "#ef4444",
          borderWidth: 2.5,
          pointBackgroundColor: "#fff",
          pointRadius: 3,
          backgroundColor: gradient,
          fill: true,
          tension: 0.25,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` PnL: ${formatINR(ctx.raw, true)}`
            }
          }
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.04)" },
            ticks: { color: "#94a3b8", font: { size: 11 } }
          },
          y: {
            grid: { color: "rgba(255, 255, 255, 0.06)" },
            ticks: {
              color: "#94a3b8",
              font: { size: 11 },
              callback: (value) => formatINR(value)
            }
          }
        }
      }
    });
  }
}

// 4. Render Tab: Statistics
function renderStats(trades) {
  const statTotal = document.getElementById("statTotalTrades");
  const statWinRate = document.getElementById("statWinRate");
  const statTotalPnl = document.getElementById("statTotalPnl");
  const statProfitFactor = document.getElementById("statProfitFactor");
  const statExpectancy = document.getElementById("statExpectancy");
  const statAvgWin = document.getElementById("statAvgWin");
  const statAvgLoss = document.getElementById("statAvgLoss");
  const statMaxDD = document.getElementById("statMaxDD");
  const statBest = document.getElementById("statBestTrade");
  const statWorst = document.getElementById("statWorstTrade");

  const setupEl = document.getElementById("statsSetupTypeContent");
  const planEl = document.getElementById("statsPlanDisciplineContent");
  const mistakesEl = document.getElementById("statsMistakesContent");

  if (!trades || trades.length === 0) {
    if (statTotal) statTotal.textContent = "0";
    if (statWinRate) statWinRate.textContent = "0.0%";
    if (statTotalPnl) statTotalPnl.textContent = "₹0.00";
    if (statProfitFactor) statProfitFactor.textContent = "0.00";
    if (statExpectancy) statExpectancy.textContent = "₹0.00";
    if (statAvgWin) statAvgWin.textContent = "+₹0.00";
    if (statAvgLoss) statAvgLoss.textContent = "-₹0.00";
    if (statMaxDD) statMaxDD.textContent = "₹0.00";
    if (statBest) statBest.textContent = "+₹0.00";
    if (statWorst) statWorst.textContent = "-₹0.00";

    if (setupEl) setupEl.innerHTML = `<div class="empty-state-sm">No trades recorded yet to analyze setup types.</div>`;
    if (planEl) planEl.innerHTML = `<div class="empty-state-sm">No trades recorded yet to analyze plan discipline.</div>`;
    if (mistakesEl) mistakesEl.innerHTML = `<div class="empty-state-sm">No trades recorded yet to track mistakes.</div>`;
    return;
  }

  const totalTrades = trades.length;
  const wins = trades.filter(t => (parseFloat(t.pnl) || 0) > 0);
  const losses = trades.filter(t => (parseFloat(t.pnl) || 0) <= 0);

  const winRate = (wins.length / totalTrades) * 100.0;
  const sumWins = wins.reduce((acc, t) => acc + (parseFloat(t.pnl) || 0), 0);
  const sumLosses = losses.reduce((acc, t) => acc + (parseFloat(t.pnl) || 0), 0);
  const totalPnl = sumWins + sumLosses;

  const avgWin = wins.length > 0 ? (sumWins / wins.length) : 0;
  const avgLoss = losses.length > 0 ? (sumLosses / losses.length) : 0;

  let profitFactorStr = "0.00";
  if (sumLosses !== 0) {
    profitFactorStr = (sumWins / Math.abs(sumLosses)).toFixed(2);
  } else if (sumWins > 0) {
    profitFactorStr = "∞";
  }

  const winProb = wins.length / totalTrades;
  const lossProb = 1.0 - winProb;
  const expectancy = (winProb * avgWin) - (lossProb * Math.abs(avgLoss));

  // Max Drawdown calculation
  let cum = 0;
  let peak = 0;
  let maxDD = 0;
  for (const t of trades) {
    cum += (parseFloat(t.pnl) || 0);
    if (cum > peak) peak = cum;
    const dd = peak - cum;
    if (dd > maxDD) maxDD = dd;
  }

  const pnls = trades.map(t => parseFloat(t.pnl) || 0);
  const bestTrade = Math.max(...pnls);
  const worstTrade = Math.min(...pnls);

  if (statTotal) statTotal.textContent = `${totalTrades} (${wins.length}W / ${losses.length}L)`;
  if (statWinRate) statWinRate.textContent = `${winRate.toFixed(1)}%`;
  if (statTotalPnl) {
    statTotalPnl.textContent = formatINR(totalPnl, true);
    statTotalPnl.className = `stat-value ${totalPnl >= 0 ? "positive" : "negative"}`;
  }

  if (statProfitFactor) statProfitFactor.textContent = profitFactorStr;
  if (statExpectancy) {
    statExpectancy.textContent = formatINR(expectancy, true);
    statExpectancy.className = `stat-value ${expectancy >= 0 ? "positive" : "negative"}`;
  }

  if (statAvgWin) statAvgWin.textContent = `+${formatINR(avgWin)}`;
  if (statAvgLoss) statAvgLoss.textContent = `-${formatINR(Math.abs(avgLoss))}`;
  if (statMaxDD) statMaxDD.textContent = `-${formatINR(maxDD)}`;

  if (statBest) statBest.textContent = formatINR(bestTrade, true);
  if (statWorst) statWorst.textContent = formatINR(worstTrade, true);

  // 1. "By setup type" block: win rate for #breakout vs #pullback
  if (setupEl) {
    const breakoutTrades = trades.filter(t => (t.tags || []).some(tag => String(tag).trim().toLowerCase() === "#breakout"));
    const pullbackTrades = trades.filter(t => (t.tags || []).some(tag => String(tag).trim().toLowerCase() === "#pullback"));

    const breakoutWins = breakoutTrades.filter(t => (parseFloat(t.pnl) || 0) > 0);
    const pullbackWins = pullbackTrades.filter(t => (parseFloat(t.pnl) || 0) > 0);

    const breakoutWinRate = breakoutTrades.length > 0
      ? ((breakoutWins.length / breakoutTrades.length) * 100).toFixed(1) + "%"
      : "N/A";
    const pullbackWinRate = pullbackTrades.length > 0
      ? ((pullbackWins.length / pullbackTrades.length) * 100).toFixed(1) + "%"
      : "N/A";

    const breakoutPnl = breakoutTrades.reduce((acc, t) => acc + (parseFloat(t.pnl) || 0), 0);
    const pullbackPnl = pullbackTrades.reduce((acc, t) => acc + (parseFloat(t.pnl) || 0), 0);

    setupEl.innerHTML = `
      <div class="stats-compare-row">
        <div class="stats-compare-label">
          <div class="stats-compare-title"><span class="tag-pill tag-breakout">#breakout</span> Setup</div>
          <div class="stats-compare-subtitle">${breakoutTrades.length} trade${breakoutTrades.length === 1 ? "" : "s"} (${breakoutWins.length}W / ${breakoutTrades.length - breakoutWins.length}L)</div>
        </div>
        <div class="stats-compare-val">
          <span class="stats-compare-metric ${breakoutWinRate !== "N/A" && parseFloat(breakoutWinRate) >= 50 ? "positive" : (breakoutWinRate === "N/A" ? "" : "negative")}">${breakoutWinRate}</span>
          <span class="stats-compare-subtitle" style="color: ${breakoutPnl >= 0 ? "var(--success)" : "var(--danger)"}">${formatINR(breakoutPnl, true)}</span>
        </div>
      </div>
      <div class="stats-compare-row">
        <div class="stats-compare-label">
          <div class="stats-compare-title"><span class="tag-pill tag-pullback">#pullback</span> Setup</div>
          <div class="stats-compare-subtitle">${pullbackTrades.length} trade${pullbackTrades.length === 1 ? "" : "s"} (${pullbackWins.length}W / ${pullbackTrades.length - pullbackWins.length}L)</div>
        </div>
        <div class="stats-compare-val">
          <span class="stats-compare-metric ${pullbackWinRate !== "N/A" && parseFloat(pullbackWinRate) >= 50 ? "positive" : (pullbackWinRate === "N/A" ? "" : "negative")}">${pullbackWinRate}</span>
          <span class="stats-compare-subtitle" style="color: ${pullbackPnl >= 0 ? "var(--success)" : "var(--danger)"}">${formatINR(pullbackPnl, true)}</span>
        </div>
      </div>
    `;
  }

  // 2. "Plan discipline" block: win rate and count for trades tagged #plan_followed vs not
  if (planEl) {
    const planTrades = trades.filter(t => (t.tags || []).some(tag => String(tag).trim().toLowerCase() === "#plan_followed"));
    const noPlanTrades = trades.filter(t => !(t.tags || []).some(tag => String(tag).trim().toLowerCase() === "#plan_followed"));

    const planWins = planTrades.filter(t => (parseFloat(t.pnl) || 0) > 0);
    const noPlanWins = noPlanTrades.filter(t => (parseFloat(t.pnl) || 0) > 0);

    const planWinRate = planTrades.length > 0
      ? ((planWins.length / planTrades.length) * 100).toFixed(1) + "%"
      : "N/A";
    const noPlanWinRate = noPlanTrades.length > 0
      ? ((noPlanWins.length / noPlanTrades.length) * 100).toFixed(1) + "%"
      : "N/A";

    const planPnl = planTrades.reduce((acc, t) => acc + (parseFloat(t.pnl) || 0), 0);
    const noPlanPnl = noPlanTrades.reduce((acc, t) => acc + (parseFloat(t.pnl) || 0), 0);

    planEl.innerHTML = `
      <div class="stats-compare-row">
        <div class="stats-compare-label">
          <div class="stats-compare-title"><span class="tag-pill tag-plan">#plan_followed</span></div>
          <div class="stats-compare-subtitle">${planTrades.length} trade${planTrades.length === 1 ? "" : "s"} (${planWins.length}W / ${planTrades.length - planWins.length}L)</div>
        </div>
        <div class="stats-compare-val">
          <span class="stats-compare-metric ${planWinRate !== "N/A" && parseFloat(planWinRate) >= 50 ? "positive" : (planWinRate === "N/A" ? "" : "negative")}">${planWinRate}</span>
          <span class="stats-compare-subtitle" style="color: ${planPnl >= 0 ? "var(--success)" : "var(--danger)"}">${formatINR(planPnl, true)}</span>
        </div>
      </div>
      <div class="stats-compare-row">
        <div class="stats-compare-label">
          <div class="stats-compare-title"><span style="color: var(--text-muted); font-size: 13px; font-weight: 600;">Not Tagged / Deviated</span></div>
          <div class="stats-compare-subtitle">${noPlanTrades.length} trade${noPlanTrades.length === 1 ? "" : "s"} (${noPlanWins.length}W / ${noPlanTrades.length - noPlanWins.length}L)</div>
        </div>
        <div class="stats-compare-val">
          <span class="stats-compare-metric ${noPlanWinRate !== "N/A" && parseFloat(noPlanWinRate) >= 50 ? "positive" : (noPlanWinRate === "N/A" ? "" : "negative")}">${noPlanWinRate}</span>
          <span class="stats-compare-subtitle" style="color: ${noPlanPnl >= 0 ? "var(--success)" : "var(--danger)"}">${formatINR(noPlanPnl, true)}</span>
        </div>
      </div>
    `;
  }

  // 3. "Mistakes" block: counting each mistake type
  if (mistakesEl) {
    const stopMovedTrades = trades.filter(t => t.mistake === "stop_moved");
    const timeStopTrades = trades.filter(t => t.mistake === "time_stop_ignored");
    const cleanTrades = trades.filter(t => !t.mistake);

    mistakesEl.innerHTML = `
      <div class="stats-mistake-item ${stopMovedTrades.length > 0 ? "" : "stats-mistake-clean"}">
        <div class="stats-compare-label">
          <div class="stats-compare-title" style="color: ${stopMovedTrades.length > 0 ? "var(--danger)" : "var(--text-dim)"};">
            ${stopMovedTrades.length > 0 ? "⚠️" : "✓"} Stop Moved (stop_moved)
          </div>
          <div class="stats-compare-subtitle">Exit price was worse than planned stop</div>
        </div>
        <div class="stats-compare-val">
          <span class="stats-compare-metric ${stopMovedTrades.length > 0 ? "negative" : "positive"}">${stopMovedTrades.length}</span>
          <span class="stats-compare-subtitle">${stopMovedTrades.length === 1 ? "1 trade" : `${stopMovedTrades.length} trades`}</span>
        </div>
      </div>

      <div class="stats-mistake-item ${timeStopTrades.length > 0 ? "" : "stats-mistake-clean"}">
        <div class="stats-compare-label">
          <div class="stats-compare-title" style="color: ${timeStopTrades.length > 0 ? "var(--danger)" : "var(--text-dim)"};">
            ${timeStopTrades.length > 0 ? "⚠️" : "✓"} Time Stop Ignored (time_stop_ignored)
          </div>
          <div class="stats-compare-subtitle">Held &gt; 5 days with return &lt; 3%</div>
        </div>
        <div class="stats-compare-val">
          <span class="stats-compare-metric ${timeStopTrades.length > 0 ? "negative" : "positive"}">${timeStopTrades.length}</span>
          <span class="stats-compare-subtitle">${timeStopTrades.length === 1 ? "1 trade" : `${timeStopTrades.length} trades`}</span>
        </div>
      </div>

      <div class="stats-mistake-item stats-mistake-clean">
        <div class="stats-compare-label">
          <div class="stats-compare-title" style="color: var(--success);">
            🛡️ Clean Discipline Executions
          </div>
          <div class="stats-compare-subtitle">No recorded rule or discipline mistakes</div>
        </div>
        <div class="stats-compare-val">
          <span class="stats-compare-metric positive">${cleanTrades.length}</span>
          <span class="stats-compare-subtitle">${trades.length > 0 ? ((cleanTrades.length / trades.length) * 100).toFixed(0) + "% clean" : "0 trades"}</span>
        </div>
      </div>
    `;
  }

  // Update Discipline Index Card (Phase 3 Item #9)
  const statDisciplineIndex = document.getElementById("statDisciplineIndex");
  const statDisciplineSub = document.getElementById("statDisciplineSub");
  if (statDisciplineIndex) {
    const totalTrades = trades.length;
    const cleanTrades = trades.filter(t => {
      if (t.mistake) return false;
      const pm = getTradePostMortem(t.symbol, t.entry_date);
      if (pm && pm.tags) {
        if (pm.tags.includes("#StopMoved") || pm.tags.includes("#ChasedGap") || pm.tags.includes("#RevengeTrade")) {
          return false;
        }
      }
      return true;
    });

    const discPct = totalTrades > 0 ? Math.round((cleanTrades.length / totalTrades) * 100) : 100;
    statDisciplineIndex.textContent = `${discPct}%`;
    statDisciplineIndex.className = `stat-value ${discPct >= 80 ? "positive" : (discPct >= 60 ? "neutral" : "negative")}`;
    if (statDisciplineSub) {
      const mistakesCount = totalTrades - cleanTrades.length;
      statDisciplineSub.textContent = mistakesCount === 0 ? "100% adhered to plan" : `${mistakesCount} rule deviation${mistakesCount === 1 ? '' : 's'}`;
    }
  }
}

// =====================================================================
// MASTER LOAD AND AUTO-REFRESH
// =====================================================================
async function loadAllData() {
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.textContent = "⏳ Updating...";
  }

  let scanData = null;
  let openPositions = null;
  let trades = null;
  let hasError = false;
  let firstErrorCode = null;

  try {
    // Fetch all core datasets via single data layer loadFile(name)
    const [sData, opData, tData] = await Promise.all([
      loadFile("scan_results.json"),
      loadFile("open_positions.json"),
      loadFile("trades.json"),
    ]);
    scanData = sData;
    openPositions = opData || [];
    trades = tData || [];

    if (scanData && openPositions && trades) {
      hideDataLinkError();
    }
  } catch (err) {
    console.error("Global dashboard data load error:", err);
  }

  try {
    _liveScanData = scanData;
    _cachedOpenPositions = openPositions || [];
    _cachedTradesData = trades || [];

    if (scanData) {
      archiveScanData(scanData);
    }

    if (scanData || (openPositions && openPositions.length > 0) || (trades && trades.length > 0)) {
      if (!_isViewingArchive) {
        renderNearBuy(scanData, _cachedOpenPositions);
      }
      await renderOpenPositions(_cachedOpenPositions);
      renderHistory(_cachedTradesData);
      renderStats(_cachedTradesData);
    }

    // Fetch and render Backtest results (Fail-open)
    let backtestData = null;
    try {
      backtestData = await loadFile("backtest_results.json");
    } catch {
      // Fail-open: backtest data optional / not yet generated
    }
    _cachedBacktestData = backtestData;
    renderBacktestTab(backtestData);
  } catch (renderErr) {
    console.error("Error rendering dashboard data:", renderErr);
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.textContent = "🔄 Refresh";
    }
    // Final check: if error occurred and no cached data was rendered, ensure Loading... is stopped
    if (hasError && !scanData && (!openPositions || openPositions.length === 0)) {
      showDataLinkError(firstErrorCode);
    }
  }
}

// =====================================================================
// HELP CENTER & HANDBOOK HELPERS
// =====================================================================
function initHelpCenter() {
  // 1. Floating circular '?' button
  const floatingHelpBtn = document.getElementById("floatingHelpBtn");
  const helpTabBtn = document.getElementById("helpTabBtn");
  if (floatingHelpBtn && helpTabBtn) {
    floatingHelpBtn.addEventListener("click", () => {
      helpTabBtn.click();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // 2. Glossary live search
  const searchInput = document.getElementById("glossarySearchInput");
  const glossaryGrid = document.getElementById("glossaryGrid");
  if (searchInput && glossaryGrid) {
    const cards = glossaryGrid.querySelectorAll(".glossary-card");
    searchInput.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase().trim();
      cards.forEach(card => {
        const text = card.textContent.toLowerCase();
        if (!q || text.includes(q)) {
          card.style.display = "flex";
        } else {
          card.style.display = "none";
        }
      });
    });
  }

  // 3. FAQ Accordion toggle
  const faqItems = document.querySelectorAll(".faq-item");
  faqItems.forEach(item => {
    const question = item.querySelector(".faq-question");
    if (question) {
      question.addEventListener("click", () => {
        item.classList.toggle("active");
      });
    }
  });

  // 4. Sticky TOC active state handling
  const tocLinks = document.querySelectorAll(".help-toc-link");
  tocLinks.forEach(link => {
    link.addEventListener("click", () => {
      tocLinks.forEach(l => l.classList.remove("active"));
      link.classList.add("active");
    });
  });

  // Scrollspy for TOC
  const sections = document.querySelectorAll(".help-section");
  if (sections.length > 0 && tocLinks.length > 0) {
    window.addEventListener("scroll", () => {
      let currentId = "";
      sections.forEach(sec => {
        const top = sec.getBoundingClientRect().top;
        if (top <= 200) {
          currentId = sec.getAttribute("id");
        }
      });
      if (currentId) {
        tocLinks.forEach(l => {
          if (l.getAttribute("href") === `#${currentId}`) {
            l.classList.add("active");
          } else {
            l.classList.remove("active");
          }
        });
      }
    }, { passive: true });
  }
}

// =====================================================================
// TERM SEARCH, INLINE DEFINITIONS & TAB BANNERS
// =====================================================================

// Helper to switch to Help tab and flash target glossary card
function jumpToHelpTerm(anchor) {
  const helpTabBtn = document.getElementById("helpTabBtn");
  if (helpTabBtn) {
    helpTabBtn.click();
  }
  if (!anchor) return;

  setTimeout(() => {
    const el = document.getElementById(anchor);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.remove("term-highlight-flash");
      void el.offsetWidth; // trigger reflow
      el.classList.add("term-highlight-flash");
      setTimeout(() => el.classList.remove("term-highlight-flash"), 2600);
    }
  }, 120);
}

// Show term definition popover positioned near targetElement
function showTermPopover(termKey, targetElement) {
  const popover = document.getElementById("termPopover");
  if (!popover) return;

  // Search case-insensitive match in TERMS
  const normKey = Object.keys(TERMS).find(k => k.toLowerCase() === termKey.toLowerCase()) || termKey;
  const termData = TERMS[normKey];
  if (!termData) return;

  document.getElementById("termPopoverTitle").textContent = normKey;
  document.getElementById("termPopoverBody").textContent = termData.short;
  document.getElementById("termPopoverWhere").textContent = termData.where_used ? `Used in: ${termData.where_used}` : "";

  const guideLink = document.getElementById("termPopoverGuideLink");
  if (termData.anchor) {
    guideLink.style.display = "inline-block";
    guideLink.onclick = (e) => {
      e.preventDefault();
      popover.style.display = "none";
      jumpToHelpTerm(termData.anchor);
    };
  } else {
    guideLink.style.display = "none";
  }

  popover.style.display = "flex";
  const rect = targetElement.getBoundingClientRect();
  const popoverWidth = 320;
  let left = rect.left + window.scrollX;
  let top = rect.bottom + window.scrollY + 8;

  // Viewport clamping
  if (left + popoverWidth > window.innerWidth - 20) {
    left = window.innerWidth - popoverWidth - 20;
  }
  if (left < 10) left = 10;

  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

function hideTermPopover() {
  const popover = document.getElementById("termPopover");
  if (popover) {
    popover.style.display = "none";
  }
}

// Global Term Search Modal State & Handlers
let currentSearchIndex = -1;

function openTermSearchModal() {
  const modal = document.getElementById("termSearchModal");
  const input = document.getElementById("termSearchInput");
  if (!modal || !input) return;
  modal.style.display = "flex";
  input.value = "";
  currentSearchIndex = -1;
  renderTermSearchResults("");
  input.focus();
}

function closeTermSearchModal() {
  const modal = document.getElementById("termSearchModal");
  if (modal) {
    modal.style.display = "none";
  }
}

function renderTermSearchResults(query) {
  const resultsContainer = document.getElementById("termSearchResults");
  if (!resultsContainer) return;

  const q = (query || "").toLowerCase().trim();
  const entries = Object.entries(TERMS);

  const matched = entries.filter(([name, data]) => {
    if (!q) return true;
    const matchName = name.toLowerCase().includes(q);
    const matchShort = data.short.toLowerCase().includes(q);
    const matchLong = (data.long || "").toLowerCase().includes(q);
    const matchWhere = (data.where_used || "").toLowerCase().includes(q);
    return matchName || matchShort || matchLong || matchWhere;
  });

  if (matched.length === 0) {
    resultsContainer.innerHTML = `
      <div class="term-search-empty">
        No terms found matching "<strong>${escapeHtml(query)}</strong>". Try searching for SMA, ATR, PnL, or Grade.
      </div>
    `;
    currentSearchIndex = -1;
    return;
  }

  resultsContainer.innerHTML = matched.map(([name, data], idx) => `
    <div class="term-search-item ${idx === currentSearchIndex ? "selected" : ""}" data-term="${escapeHtml(name)}" data-anchor="${data.anchor || ""}">
      <div class="term-search-item-top">
        <span class="term-search-item-title">${escapeHtml(name)}</span>
        ${data.where_used ? `<span class="term-search-item-where">${escapeHtml(data.where_used)}</span>` : ""}
      </div>
      <div class="term-search-item-meaning">${escapeHtml(data.short)}</div>
    </div>
  `).join("");

  // Attach click handlers
  resultsContainer.querySelectorAll(".term-search-item").forEach(item => {
    item.addEventListener("click", () => {
      const termName = item.getAttribute("data-term");
      const anchor = item.getAttribute("data-anchor");
      closeTermSearchModal();
      if (anchor) {
        jumpToHelpTerm(anchor);
      } else {
        showTermPopover(termName, item);
      }
    });
  });
}

// "How to read this tab" Dismissible Info Banners
function initTabGuideBanners() {
  const banners = document.querySelectorAll(".tab-guide-banner");
  banners.forEach(banner => {
    const bannerKey = banner.getAttribute("data-tab-banner");
    const storageKey = `dismissed_tab_banner_${bannerKey}`;
    if (localStorage.getItem(storageKey) === "1") {
      banner.style.display = "none";
      return;
    }

    const dismissBtn = banner.querySelector(".tab-guide-dismiss");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", () => {
        banner.classList.add("dismissing");
        localStorage.setItem(storageKey, "1");
        setTimeout(() => {
          banner.style.display = "none";
        }, 220);
      });
    }
  });
}

// Initialize Global Search and Clickable Term Lookups
function initTermSearchAndLookups() {
  // Magnifier button in top bar
  const globalSearchBtn = document.getElementById("globalSearchBtn");
  if (globalSearchBtn) {
    globalSearchBtn.addEventListener("click", openTermSearchModal);
  }

  // Search backdrop click
  const backdrop = document.getElementById("termSearchBackdrop");
  if (backdrop) {
    backdrop.addEventListener("click", closeTermSearchModal);
  }

  // Search input typing
  const searchInput = document.getElementById("termSearchInput");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentSearchIndex = -1;
      renderTermSearchResults(e.target.value);
    });

    // Arrow navigation & Enter selection
    searchInput.addEventListener("keydown", (e) => {
      const items = document.querySelectorAll("#termSearchResults .term-search-item");
      if (items.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        currentSearchIndex = (currentSearchIndex + 1) % items.length;
        items.forEach((it, idx) => {
          if (idx === currentSearchIndex) {
            it.classList.add("selected");
            it.scrollIntoView({ block: "nearest" });
          } else {
            it.classList.remove("selected");
          }
        });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        currentSearchIndex = (currentSearchIndex - 1 + items.length) % items.length;
        items.forEach((it, idx) => {
          if (idx === currentSearchIndex) {
            it.classList.add("selected");
            it.scrollIntoView({ block: "nearest" });
          } else {
            it.classList.remove("selected");
          }
        });
      } else if (e.key === "Enter") {
        e.preventDefault();
        const target = currentSearchIndex >= 0 && currentSearchIndex < items.length
          ? items[currentSearchIndex]
          : items[0];
        if (target) target.click();
      }
    });
  }

  // Keyboard shortcuts: "/" to open, "Escape" to close
  document.addEventListener("keydown", (e) => {
    if (e.key === "/") {
      const activeEl = document.activeElement;
      const isInput = activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "TEXTAREA" || activeEl.isContentEditable);
      if (!isInput) {
        e.preventDefault();
        openTermSearchModal();
      }
    } else if (e.key === "Escape") {
      const modal = document.getElementById("termSearchModal");
      if (modal && modal.style.display !== "none") {
        closeTermSearchModal();
      }
      hideTermPopover();
    }
  });

  // Popover close button
  const popoverClose = document.getElementById("termPopoverClose");
  if (popoverClose) {
    popoverClose.addEventListener("click", hideTermPopover);
  }

  // Clickable terms event delegation across all tabs
  document.addEventListener("click", (e) => {
    const lookupEl = e.target.closest(".term-lookup");
    if (lookupEl) {
      e.preventDefault();
      e.stopPropagation();
      const termKey = lookupEl.getAttribute("data-term") || lookupEl.textContent.trim();
      showTermPopover(termKey, lookupEl);
      return;
    }

    // Outside click closes popover
    const popover = document.getElementById("termPopover");
    if (popover && popover.style.display !== "none" && !popover.contains(e.target)) {
      hideTermPopover();
    }
  });
}

// =====================================================================
// EVENT LISTENERS & INITIALIZATION
// =====================================================================
document.addEventListener("DOMContentLoaded", () => {
  // Authentication gate for dashboard
  if (window.location.pathname.endsWith("app.html")) {
    if (localStorage.getItem("auth") !== "1") {
      window.location.href = "index.html";
      return;
    }
  }

  // Logout button - CLEAR dash_key_hash and auth
  const logoutBtn = document.getElementById("logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      localStorage.removeItem("auth");
      localStorage.removeItem("dash_key_hash");
      window.location.href = "index.html";
    });
  }

  // Refresh button
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadAllData();
    });
  }

  // Tab switching
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTabId = btn.getAttribute("data-tab");

      tabButtons.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.classList.remove("active"));

      btn.classList.add("active");
      const targetContent = document.getElementById(targetTabId);
      if (targetContent) {
        targetContent.classList.add("active");
      }
    });
  });

  // Initialize Help Center
  initHelpCenter();

  // Initialize Term Search, Inline Definitions & Tab Banners
  initTabGuideBanners();
  initTermSearchAndLookups();

  // Initialize TradingView Modal Listeners (Phase 2 Item #3)
  initTradingViewModalListeners();

  // Initialize Phase 3 Listeners (Items #7, #8, #9, #10)
  initGttListeners();
  initScanArchiveListeners();
  initPostMortemListeners();
  initCsvExportListeners();

  // Initialize SC-3 Collapsible Sections (Leaders Board & On Deck)
  initCollapsibleSections();

  // Initialize SC-5 Backtest Tab Listeners
  initBacktestListeners();

  // Initialize SC-6 Trader's Playbook Listeners (Buy & Sell Cards)
  initPlaybookListeners();

  // Keep IST Live chip ticking every 30 seconds
  setInterval(updateIstLiveChip, 30000);

  // Initial load if on app page
  if (document.getElementById("watchlistTable")) {
    initPositionSizer();
    loadAllData();

    // Auto-refresh every 5 minutes (300,000 ms)
    setInterval(() => {
      console.log("Auto-refreshing dashboard data...");
      loadAllData();
    }, 300000);
  }
});

// =====================================================================
// TRADINGVIEW INTERACTIVE CHART MODAL (Item #3)
// =====================================================================
function openTradingViewModal(symbol) {
  if (!symbol) return;
  const cleanSym = symbol.replace(/\.NS$/i, "").toUpperCase();
  const modal = document.getElementById("tvChartModal");
  const modalTitle = document.getElementById("tvModalTitle");
  const externalLink = document.getElementById("tvExternalLink");
  const widgetContainer = document.getElementById("tvWidgetContainer");

  if (!modal || !widgetContainer) return;

  if (modalTitle) modalTitle.textContent = `Interactive Chart: NSE:${cleanSym}`;
  if (externalLink) {
    externalLink.href = `https://in.tradingview.com/chart/?symbol=NSE%3A${cleanSym}`;
  }

  // Official TradingView widget iframe embed with dark theme, Indian market timezone, and moving averages
  const widgetUrl = `https://s.tradingview.com/widgetembed/?frameElementId=tradingview_widget&symbol=NSE%3A${cleanSym}&interval=D&hidesidetoolbar=0&symboledit=1&saveimage=1&toolbarbg=111827&studies=MASimple%40tv-basicstudies%1FMASimple%40tv-basicstudies%1FRSI%40tv-basicstudies&theme=dark&style=1&timezone=Asia%2FKolkata&withdateranges=1&hideideas=1`;

  widgetContainer.innerHTML = `
    <iframe
      src="${widgetUrl}"
      style="width: 100%; height: 100%; border: none; border-radius: 0 0 12px 12px;"
      allowtransparency="true"
      scrolling="no"
      allowfullscreen>
    </iframe>
  `;

  modal.style.display = "flex";
  document.body.style.overflow = "hidden"; // Prevent background scrolling
}

function closeTradingViewModal() {
  const modal = document.getElementById("tvChartModal");
  const widgetContainer = document.getElementById("tvWidgetContainer");
  if (modal) modal.style.display = "none";
  if (widgetContainer) widgetContainer.innerHTML = ""; // Clear iframe to free memory and stop audio/network
  document.body.style.overflow = "";
}

function initTradingViewModalListeners() {
  const modal = document.getElementById("tvChartModal");
  const backdrop = document.getElementById("tvModalBackdrop");
  const closeBtn = document.getElementById("tvModalCloseBtn");

  if (closeBtn) {
    closeBtn.addEventListener("click", closeTradingViewModal);
  }
  if (backdrop) {
    backdrop.addEventListener("click", closeTradingViewModal);
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && modal.style.display === "flex") {
      closeTradingViewModal();
    }
  });

  // Delegate click for any .tv-chart-trigger-btn on document
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".tv-chart-trigger-btn");
    if (btn) {
      const sym = btn.getAttribute("data-symbol");
      if (sym) {
        e.stopPropagation();
        openTradingViewModal(sym);
      }
    }
  });
}

// =====================================================================
// PHASE 3: GLOBAL FLOATING TOAST NOTIFICATION
// =====================================================================
function showToast(message, icon = "✅", duration = 3000) {
  const toast = document.getElementById("dashboardToast");
  const msgEl = document.getElementById("toastMessage");
  const iconEl = document.getElementById("toastIcon");
  if (!toast) return;
  if (msgEl) msgEl.textContent = message;
  if (iconEl) iconEl.textContent = icon;
  toast.style.display = "flex";
  void toast.offsetWidth;
  toast.classList.add("show");
  if (window._toastTimeout) clearTimeout(window._toastTimeout);
  window._toastTimeout = setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => { toast.style.display = "none"; }, 300);
  }, duration);
}

// =====================================================================
// PHASE 3: BROKER GTT ORDER COPY ASSISTANT (Item #7)
// =====================================================================
function copyGttParameters(symbol, entry, stop, target, qty) {
  const sym = (symbol || "").replace(/\.NS$/i, "").toUpperCase();
  const ePrice = parseFloat(entry) || 0;
  const sPrice = parseFloat(stop) || 0;
  const tPrice = parseFloat(target) || 0;
  const q = parseInt(qty, 10) || 1;

  // Buffer: Stop limit 0.5% below trigger for fast market depth protection
  const stopLimit = (sPrice * 0.995).toFixed(2);
  const targetTrigger = tPrice.toFixed(2);

  const gttText = `[GTT ORDER: NSE:${sym}]
Broker: Zerodha Kite / Groww / Upstox
• Stop Loss Trigger: ₹${sPrice.toFixed(2)}
• Stop Loss Limit: ₹${stopLimit} (0.5% buffer)
• Target Trigger: ₹${targetTrigger}
• Qty: ${q}
• Entry Ref: ₹${ePrice.toFixed(2)}`;

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(gttText).then(() => {
      showToast(`Copied GTT Stop for ${sym}: Trigger ₹${sPrice.toFixed(2)}`, "📋");
    }).catch(() => {
      prompt("Copy GTT snippet:", gttText);
    });
  } else {
    prompt("Copy GTT snippet:", gttText);
  }
}

function initGttListeners() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".gtt-copy-btn");
    if (btn) {
      e.stopPropagation();
      const sym = btn.getAttribute("data-symbol");
      const entry = btn.getAttribute("data-entry");
      const stop = btn.getAttribute("data-stop");
      const target = btn.getAttribute("data-target");
      const qty = btn.getAttribute("data-qty") || 1;
      copyGttParameters(sym, entry, stop, target, qty);
    }
  });
}

// =====================================================================
// PHASE 3: LOCAL SCAN HISTORY & RETROSPECTIVE ARCHIVE (Item #8)
// =====================================================================
function archiveScanData(data) {
  if (!data || !data.watchlist) return;
  try {
    const scanTime = data.scan_time || new Date().toISOString();
    const dateKey = scanTime.substring(0, 10);
    const storageKey = "smallcap_scan_archive";
    const existingStr = localStorage.getItem(storageKey);
    const archive = existingStr ? JSON.parse(existingStr) : {};

    archive[dateKey] = {
      date: dateKey,
      scan_time: scanTime,
      market_regime: data.market_regime,
      market_ok: data.market_ok,
      scanned_count: data.scanned_count,
      watchlist: data.watchlist,
      signals: data.signals || []
    };

    const dates = Object.keys(archive).sort().reverse();
    if (dates.length > 30) {
      dates.slice(30).forEach(d => delete archive[d]);
    }
    localStorage.setItem(storageKey, JSON.stringify(archive));
    updateArchiveDropdown();
  } catch (err) {
    console.warn("Could not archive scan data to localStorage:", err);
  }
}

function updateArchiveDropdown() {
  const select = document.getElementById("watchlistDateSelect");
  if (!select) return;
  try {
    const storageKey = "smallcap_scan_archive";
    const existingStr = localStorage.getItem(storageKey);
    const archive = existingStr ? JSON.parse(existingStr) : {};
    const dates = Object.keys(archive).sort().reverse();

    const currentVal = select.value || "latest";
    let optionsHtml = '<option value="latest">Latest (Live)</option>';
    dates.forEach(d => {
      const count = archive[d].watchlist ? archive[d].watchlist.length : 0;
      optionsHtml += `<option value="${d}">${d} (${count} setups)</option>`;
    });
    select.innerHTML = optionsHtml;
    if (currentVal && (currentVal === "latest" || dates.includes(currentVal))) {
      select.value = currentVal;
    }
  } catch (err) {}
}

function initScanArchiveListeners() {
  const select = document.getElementById("watchlistDateSelect");
  const returnBtn = document.getElementById("returnToLatestScanBtn");
  const banner = document.getElementById("archiveScanNoticeBanner");
  const bannerText = document.getElementById("archiveNoticeText");

  if (select) {
    select.addEventListener("change", () => {
      const val = select.value;
      if (val === "latest" || !val) {
        _isViewingArchive = false;
        if (banner) banner.style.display = "none";
        if (_liveScanData) {
          renderNearBuy(_liveScanData, _cachedOpenPositions);
        }
      } else {
        try {
          const archive = JSON.parse(localStorage.getItem("smallcap_scan_archive") || "{}");
          const archivedScan = archive[val];
          if (archivedScan) {
            _isViewingArchive = true;
            if (bannerText) {
              bannerText.innerHTML = `Viewing <strong>Historical Scan Archive: ${escapeHtml(val)}</strong> (${archivedScan.watchlist ? archivedScan.watchlist.length : 0} setups recorded)`;
            }
            if (banner) banner.style.display = "flex";
            renderNearBuy(archivedScan, _cachedOpenPositions);
            showToast(`Loaded historical scan for ${val}`, "🕒");
          }
        } catch (err) {
          console.error("Failed to load archived scan:", err);
        }
      }
    });
  }

  if (returnBtn) {
    returnBtn.addEventListener("click", () => {
      if (select) select.value = "latest";
      _isViewingArchive = false;
      if (banner) banner.style.display = "none";
      if (_liveScanData) {
        renderNearBuy(_liveScanData, _cachedOpenPositions);
        showToast("Returned to live scan", "🟢");
      }
    });
  }
}

// =====================================================================
// PHASE 3: TRADE POST-MORTEM & REFLECTION NOTES (Item #9)
// =====================================================================
function getTradePostMortem(symbol, entryDate) {
  if (!symbol) return null;
  const key = `smallcap_pm_${String(symbol).replace(/\.NS$/i, "").toUpperCase()}_${String(entryDate).substring(0, 10)}`;
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function saveTradePostMortem(symbol, entryDate, data) {
  if (!symbol) return;
  const key = `smallcap_pm_${String(symbol).replace(/\.NS$/i, "").toUpperCase()}_${String(entryDate).substring(0, 10)}`;
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch (e) {
    console.warn("Could not save post-mortem:", e);
  }
}

let _activePostMortemTrade = null;

function openPostMortemModal(trade) {
  _activePostMortemTrade = trade;
  const modal = document.getElementById("postMortemModal");
  const title = document.getElementById("postMortemTitle");
  const summaryStrip = document.getElementById("postMortemTradeSummary");
  const notesInput = document.getElementById("postMortemNotesInput");
  const chipContainer = document.getElementById("postMortemTagChips");

  if (!modal) return;

  const sym = (trade.symbol || "").replace(/\.NS$/i, "").toUpperCase();
  if (title) title.textContent = `Trade Post-Mortem: ${sym}`;

  const pnl = parseFloat(trade.pnl) || 0;
  const pnlSign = pnl >= 0 ? "+" : "";
  const rVal = trade.r !== undefined && trade.r !== null ? (typeof trade.r === "number" ? trade.r.toFixed(1) + "R" : trade.r) : "N/A";

  if (summaryStrip) {
    summaryStrip.innerHTML = `
      <div class="pm-sum-item">
        <span class="pm-sum-label">Dates:</span>
        <span class="pm-sum-val">${formatDate(trade.entryDate)} &rarr; ${formatDate(trade.exitDate)}</span>
      </div>
      <div class="pm-sum-item">
        <span class="pm-sum-label">PnL:</span>
        <span class="pm-sum-val ${pnl >= 0 ? 'text-success' : 'text-danger'}">${pnlSign}${formatINR(pnl)}</span>
      </div>
      <div class="pm-sum-item">
        <span class="pm-sum-label">R-Multiple:</span>
        <span class="pm-sum-val ${pnl >= 0 ? 'text-success' : 'text-danger'}">${rVal}</span>
      </div>
    `;
  }

  const saved = getTradePostMortem(sym, trade.entryDate) || { tags: [], notes: "" };
  if (notesInput) notesInput.value = saved.notes || "";

  if (chipContainer) {
    const buttons = chipContainer.querySelectorAll(".pm-tag-btn");
    buttons.forEach(btn => {
      const tag = btn.getAttribute("data-tag");
      if (saved.tags && saved.tags.includes(tag)) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  modal.style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closePostMortemModal() {
  const modal = document.getElementById("postMortemModal");
  if (modal) modal.style.display = "none";
  document.body.style.overflow = "";
  _activePostMortemTrade = null;
}

function initPostMortemListeners() {
  const modal = document.getElementById("postMortemModal");
  const backdrop = document.getElementById("postMortemBackdrop");
  const closeBtn = document.getElementById("postMortemCloseBtn");
  const cancelBtn = document.getElementById("postMortemCancelBtn");
  const saveBtn = document.getElementById("postMortemSaveBtn");
  const chipContainer = document.getElementById("postMortemTagChips");
  const notesInput = document.getElementById("postMortemNotesInput");

  if (closeBtn) closeBtn.addEventListener("click", closePostMortemModal);
  if (backdrop) backdrop.addEventListener("click", closePostMortemModal);
  if (cancelBtn) cancelBtn.addEventListener("click", closePostMortemModal);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && modal.style.display === "flex") {
      closePostMortemModal();
    }
  });

  if (chipContainer) {
    chipContainer.addEventListener("click", (e) => {
      const btn = e.target.closest(".pm-tag-btn");
      if (btn) {
        btn.classList.toggle("active");
      }
    });
  }

  if (saveBtn) {
    saveBtn.addEventListener("click", () => {
      if (!_activePostMortemTrade) return;
      const sym = _activePostMortemTrade.symbol;
      const entryDate = _activePostMortemTrade.entryDate;

      const activeTags = [];
      if (chipContainer) {
        chipContainer.querySelectorAll(".pm-tag-btn.active").forEach(btn => {
          activeTags.push(btn.getAttribute("data-tag"));
        });
      }

      const notes = notesInput ? notesInput.value.trim() : "";

      saveTradePostMortem(sym, entryDate, {
        tags: activeTags,
        notes: notes,
        updated_at: new Date().toISOString()
      });

      closePostMortemModal();
      showToast(`Saved reflection for ${sym}`, "💾");

      if (_cachedTradesData) {
        renderHistory(_cachedTradesData);
        renderStats(_cachedTradesData);
      }
    });
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".pm-edit-btn");
    if (btn) {
      e.stopPropagation();
      openPostMortemModal({
        symbol: btn.getAttribute("data-symbol"),
        entryDate: btn.getAttribute("data-entry-date"),
        exitDate: btn.getAttribute("data-exit-date"),
        pnl: btn.getAttribute("data-pnl"),
        r: btn.getAttribute("data-r")
      });
    }
  });
}

// =====================================================================
// PHASE 3: ONE-CLICK JOURNAL BACKUP & CSV EXPORT (Item #10)
// =====================================================================
function exportTradesToCsv() {
  if (!_cachedTradesData || _cachedTradesData.length === 0) {
    showToast("No closed trades to export", "⚠️");
    return;
  }

  const headers = [
    "Trade No",
    "Symbol",
    "Entry Date",
    "Entry Price (INR)",
    "Qty",
    "Capital Deployed (INR)",
    "Exit Date",
    "Exit Price (INR)",
    "Realized PnL (INR)",
    "Return (%)",
    "R-Multiple",
    "System Mistake Flag",
    "Execution Tags",
    "Trade Notes & Reflections"
  ];

  const rows = _cachedTradesData.map((t, idx) => {
    const localPm = getTradePostMortem(t.symbol, t.entry_date) || {};
    const mergedTags = [...(t.tags || []), ...(localPm.tags || [])];
    const uniqueTags = [...new Set(mergedTags)].join("; ");
    const mergedNotes = [t.note, localPm.notes].filter(Boolean).join(" | ");
    const pnl = parseFloat(t.pnl) || 0;
    const pnlPct = parseFloat(t.pnl_pct) || 0;
    const entryPrice = parseFloat(t.entry_price) || 0;
    const qty = parseInt(t.qty, 10) || 1;
    const capital = entryPrice * qty;

    const escapeCsv = (str) => `"${String(str || "").replace(/"/g, '""')}"`;

    return [
      idx + 1,
      escapeCsv(t.symbol || ""),
      escapeCsv(t.entry_date || ""),
      entryPrice.toFixed(2),
      qty,
      capital.toFixed(2),
      escapeCsv(t.exit_date || ""),
      (parseFloat(t.exit_price) || 0).toFixed(2),
      pnl.toFixed(2),
      pnlPct.toFixed(2),
      escapeCsv(t.r_multiple !== null && t.r_multiple !== undefined ? `${t.r_multiple}R` : "N/A"),
      escapeCsv(t.mistake || "none"),
      escapeCsv(uniqueTags),
      escapeCsv(mergedNotes)
    ].join(",");
  });

  const csvContent = "\uFEFF" + [headers.join(","), ...rows].join("\r\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const dateStr = new Date().toISOString().substring(0, 10);
  link.setAttribute("href", url);
  link.setAttribute("download", `smallcap_swing_trade_journal_${dateStr}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  showToast(`Exported ${rows.length} trades to CSV`, "📥");
}

function initCsvExportListeners() {
  const exportHistoryBtn = document.getElementById("exportTradesCsvBtn");
  const exportStatsBtn = document.getElementById("exportStatsCsvBtn");

  if (exportHistoryBtn) {
    exportHistoryBtn.addEventListener("click", exportTradesToCsv);
  }
  if (exportStatsBtn) {
    exportStatsBtn.addEventListener("click", exportTradesToCsv);
  }
}

// =====================================================================
// 🧪 RULES-REPLAY BACKTEST TAB (SC-5)
// =====================================================================
function renderBacktestTab(btData) {
  const emptyState = document.getElementById("btEmptyState");
  const contentWrapper = document.getElementById("btContentWrapper");
  const periodLabel = document.getElementById("backtestPeriodLabel");

  if (!btData || !btData.trades || btData.trades.length === 0) {
    if (emptyState) emptyState.style.display = "block";
    if (contentWrapper) contentWrapper.style.display = "none";
    if (periodLabel) {
      if (btData && btData.period && btData.period.start) {
        periodLabel.textContent = `Period: ${btData.period.start} to ${btData.period.end} (0 archived trades)`;
      } else {
        periodLabel.textContent = "No archived backtest runs yet";
      }
    }
    return;
  }

  if (emptyState) emptyState.style.display = "none";
  if (contentWrapper) contentWrapper.style.display = "block";

  if (periodLabel && btData.period) {
    periodLabel.textContent = `Period: ${btData.period.start} to ${btData.period.end}`;
  }

  // Populate headline stats
  const winRateEl = document.getElementById("btWinRate");
  const pfEl = document.getElementById("btProfitFactor");
  const expEl = document.getElementById("btExpectancyR");
  const ddEl = document.getElementById("btMaxDrawdown");
  const tradesEl = document.getElementById("btTotalTrades");
  const winLossEl = document.getElementById("btAvgWinLoss");

  if (winRateEl) winRateEl.textContent = `${(btData.win_rate * 100).toFixed(1)}%`;
  if (pfEl) pfEl.textContent = Number(btData.profit_factor).toFixed(2);
  if (expEl) {
    const sign = btData.expectancy_R >= 0 ? "+" : "";
    expEl.textContent = `${sign}${Number(btData.expectancy_R).toFixed(2)} R`;
    expEl.className = `bt-stat-val ${btData.expectancy_R >= 0 ? 'positive' : 'negative'}`;
  }
  if (ddEl) ddEl.textContent = `-${Number(btData.max_drawdown_pct).toFixed(1)}%`;
  if (tradesEl) tradesEl.textContent = `${btData.trades.length} Trades`;
  if (winLossEl) winLossEl.textContent = `+${btData.avg_win_R}R / ${btData.avg_loss_R}R`;

  // Tail-Capture Panel
  const tail = btData.tail_capture || {};
  const tailPctEl = document.getElementById("btTailPct");
  const tailAvgREl = document.getElementById("btTailAvgR");
  const tailDeltaEl = document.getElementById("btTailDelta");

  if (tailPctEl) tailPctEl.textContent = `${Number(tail.pct_winners_past_2R || 0).toFixed(1)}%`;
  if (tailAvgREl) tailAvgREl.textContent = `+${Number(tail.avg_R_of_tails || 0).toFixed(2)} R`;
  if (tailDeltaEl) {
    const delta = Number(tail.capped_vs_trailed_delta || 0);
    tailDeltaEl.textContent = `+${formatINR(delta)}`;
  }

  // Equity Curve Canvas
  drawBacktestChart(btData.equity_curve || []);

  // Final Equity Badge
  const finalEqBadge = document.getElementById("btFinalEquityBadge");
  if (finalEqBadge && btData.equity_curve && btData.equity_curve.length > 0) {
    const finalVal = btData.equity_curve[btData.equity_curve.length - 1].value;
    finalEqBadge.textContent = formatINR(finalVal);
    finalEqBadge.className = `badge ${finalVal >= 200000 ? 'badge-success' : 'badge-danger'}`;
  }

  // By Grade Table
  const byGradeBody = document.getElementById("btByGradeBody");
  if (byGradeBody) {
    const grades = ["A+", "A", "B", "C"];
    byGradeBody.innerHTML = grades.map(g => {
      const info = (btData.by_grade && btData.by_grade[g]) || { trades: 0, win_rate: 0, profit_factor: 0, expectancy_R: 0 };
      const wr = (info.win_rate * 100).toFixed(0);
      return `
        <tr>
          <td><span class="badge ${g === 'A+' || g === 'A' ? 'badge-success' : (g === 'B' ? 'badge-warning' : 'badge-danger')}">${g}</span></td>
          <td>${info.trades}</td>
          <td>${wr}%</td>
          <td>${Number(info.profit_factor).toFixed(2)}</td>
          <td>${info.expectancy_R >= 0 ? '+' : ''}${Number(info.expectancy_R).toFixed(2)}R</td>
        </tr>
      `;
    }).join("");
  }

  // By Type Table
  const byTypeBody = document.getElementById("btByTypeBody");
  if (byTypeBody) {
    const types = ["BREAKOUT", "PULLBACK", "SPRING"];
    byTypeBody.innerHTML = types.map(t => {
      const info = (btData.by_signal_type && btData.by_signal_type[t]) || { trades: 0, win_rate: 0, profit_factor: 0, expectancy_R: 0 };
      const wr = (info.win_rate * 100).toFixed(0);
      return `
        <tr>
          <td><span class="badge badge-neutral">${t}</span></td>
          <td>${info.trades}</td>
          <td>${wr}%</td>
          <td>${Number(info.profit_factor).toFixed(2)}</td>
          <td>${info.expectancy_R >= 0 ? '+' : ''}${Number(info.expectancy_R).toFixed(2)}R</td>
        </tr>
      `;
    }).join("");
  }

  // Closed Trades Log Table
  const tradesBody = document.getElementById("btTradesBody");
  const tradesCountBadge = document.getElementById("btTradesCountBadge");
  if (tradesCountBadge) tradesCountBadge.textContent = `${btData.trades.length} Trade${btData.trades.length === 1 ? '' : 's'}`;

  if (tradesBody) {
    tradesBody.innerHTML = btData.trades.map(t => {
      const sym = escapeHtml(t.symbol);
      const isWin = t.pnl > 0;
      const pnlClass = isWin ? "text-success" : (t.pnl < 0 ? "text-danger" : "");
      const pnlSign = isWin ? "+" : "";
      const rSign = t.r_multiple >= 0 ? "+" : "";
      const grade = escapeHtml(t.grade || "A");
      const sigType = escapeHtml(t.signal_type || "BREAKOUT");
      const reason = escapeHtml(t.exit_reason || "EXIT");

      return `
        <tr>
          <td><strong>${sym}</strong></td>
          <td><span class="badge badge-neutral" style="font-size: 10px;">${sigType}</span></td>
          <td><span class="badge ${grade === 'A+' || grade === 'A' ? 'badge-success' : 'badge-warning'}" style="font-size: 10px;">${grade}</span></td>
          <td>${t.entry_date}</td>
          <td>₹${Number(t.entry_price).toFixed(2)}</td>
          <td>${t.exit_date}</td>
          <td>₹${Number(t.exit_price).toFixed(2)}</td>
          <td><span class="badge badge-neutral" style="font-size: 10.5px;">${reason}</span></td>
          <td class="${pnlClass}"><strong>${rSign}${Number(t.r_multiple).toFixed(2)}R</strong></td>
          <td class="${pnlClass}">${pnlSign}${formatINR(t.pnl)}</td>
        </tr>
      `;
    }).join("");
  }
}

function drawBacktestChart(equityCurve) {
  const canvas = document.getElementById("backtestEquityCanvas");
  if (!canvas || typeof Chart === "undefined") return;

  if (backtestChartInstance) {
    backtestChartInstance.destroy();
  }

  if (!equityCurve || equityCurve.length === 0) return;

  const labels = equityCurve.map(pt => pt.date);
  const values = equityCurve.map(pt => pt.value);
  const drawdowns = equityCurve.map(pt => -Math.abs(pt.drawdown || 0));

  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 280);
  gradient.addColorStop(0, "rgba(16, 185, 129, 0.28)");
  gradient.addColorStop(1, "rgba(16, 185, 129, 0.0)");

  backtestChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Portfolio Equity (₹)",
          data: values,
          borderColor: "#10b981",
          borderWidth: 2,
          pointRadius: values.length > 50 ? 0 : 2,
          backgroundColor: gradient,
          fill: true,
          tension: 0.2,
          yAxisID: "y",
        },
        {
          label: "Drawdown (%)",
          data: drawdowns,
          borderColor: "rgba(239, 68, 68, 0.6)",
          borderWidth: 1.5,
          borderDash: [3, 3],
          pointRadius: 0,
          backgroundColor: "rgba(239, 68, 68, 0.08)",
          fill: true,
          tension: 0.1,
          yAxisID: "y1",
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: true, position: "top", labels: { color: "#94a3b8", font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.datasetIndex === 0) return ` Equity: ${formatINR(ctx.raw)}`;
              return ` Drawdown: ${Number(ctx.raw).toFixed(1)}%`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { color: "#94a3b8", font: { size: 10 }, maxTicksLimit: 12 }
        },
        y: {
          type: "linear",
          position: "left",
          grid: { color: "rgba(255, 255, 255, 0.06)" },
          ticks: { color: "#94a3b8", font: { size: 10 }, callback: (v) => formatINR(v) }
        },
        y1: {
          type: "linear",
          position: "right",
          grid: { display: false },
          ticks: { color: "#f87171", font: { size: 10 }, callback: (v) => `${v}%` }
        }
      }
    }
  });
}

function initBacktestListeners() {
  const filterBtn = document.getElementById("btFilterBtn");
  if (filterBtn) {
    filterBtn.addEventListener("click", () => {
      const start = document.getElementById("btStartInput")?.value;
      const end = document.getElementById("btEndInput")?.value;
      if (!_cachedBacktestData) return;

      let filteredTrades = _cachedBacktestData.trades || [];
      if (start) filteredTrades = filteredTrades.filter(t => t.entry_date >= start);
      if (end) filteredTrades = filteredTrades.filter(t => t.entry_date <= end);

      const subData = Object.assign({}, _cachedBacktestData, {
        period: { start: start || _cachedBacktestData.period?.start, end: end || _cachedBacktestData.period?.end },
        trades: filteredTrades,
      });
      renderBacktestTab(subData);
    });
  }
}

// =====================================================================
// SC-6: TRADER'S PLAYBOOK LISTENERS (Buy & Sell Cards)
// =====================================================================
function initPlaybookListeners() {
  const isMobile = window.innerWidth < 768;

  // 1. Buy Playbook Card (#playbookBuyCard)
  const buyCard = document.getElementById("playbookBuyCard");
  const buyBtn = document.getElementById("playbookBuyToggleBtn");
  const buyChevron = document.getElementById("playbookBuyChevron");
  if (buyCard && buyBtn) {
    const savedBuy = localStorage.getItem("playbook_buy_expanded");
    const buyExpanded = savedBuy !== null ? savedBuy === "true" : !isMobile;
    if (!buyExpanded) {
      buyCard.classList.add("collapsed");
      buyBtn.setAttribute("aria-expanded", "false");
      if (buyChevron) buyChevron.textContent = "▶";
    } else {
      buyCard.classList.remove("collapsed");
      buyBtn.setAttribute("aria-expanded", "true");
      if (buyChevron) buyChevron.textContent = "▼";
    }

    buyBtn.addEventListener("click", () => {
      const isCollapsed = buyCard.classList.toggle("collapsed");
      const expanded = !isCollapsed;
      buyBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
      if (buyChevron) buyChevron.textContent = expanded ? "▼" : "▶";
      localStorage.setItem("playbook_buy_expanded", expanded ? "true" : "false");
    });
  }

  // 2. Sell Playbook Card (#playbookSellCard)
  const sellCard = document.getElementById("playbookSellCard");
  const sellBtn = document.getElementById("playbookSellToggleBtn");
  const sellChevron = document.getElementById("playbookSellChevron");
  if (sellCard && sellBtn) {
    const savedSell = localStorage.getItem("playbook_sell_expanded");
    const sellExpanded = savedSell !== null ? savedSell === "true" : !isMobile;
    if (!sellExpanded) {
      sellCard.classList.add("collapsed");
      sellBtn.setAttribute("aria-expanded", "false");
      if (sellChevron) sellChevron.textContent = "▶";
    } else {
      sellCard.classList.remove("collapsed");
      sellBtn.setAttribute("aria-expanded", "true");
      if (sellChevron) sellChevron.textContent = "▼";
    }

    sellBtn.addEventListener("click", () => {
      const isCollapsed = sellCard.classList.toggle("collapsed");
      const expanded = !isCollapsed;
      sellBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
      if (sellChevron) sellChevron.textContent = expanded ? "▼" : "▶";
      localStorage.setItem("playbook_sell_expanded", expanded ? "true" : "false");
    });
  }

  // 3. Copy Formula Button (#copyFormulaBtn)
  const copyFormulaBtn = document.getElementById("copyFormulaBtn");
  if (copyFormulaBtn) {
    copyFormulaBtn.addEventListener("click", async () => {
      const formula = "size = (CAPITAL * RISK_PCT) / (Entry - SL)";
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(formula);
        } else {
          const ta = document.createElement("textarea");
          ta.value = formula;
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
        }
        const originalHtml = copyFormulaBtn.innerHTML;
        copyFormulaBtn.innerHTML = "✓ Copied!";
        copyFormulaBtn.classList.add("btn-success");
        setTimeout(() => {
          copyFormulaBtn.innerHTML = originalHtml;
          copyFormulaBtn.classList.remove("btn-success");
        }, 2000);
        showToast("Copied formula to clipboard", "📋");
      } catch (err) {
        console.warn("Failed to copy formula:", err);
      }
    });
  }
}





