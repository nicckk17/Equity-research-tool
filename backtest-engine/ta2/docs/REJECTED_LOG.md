# Rejected / not-kept strategy log (v1 Phase 2, Oct-Nov 2026)

**Check here before testing any idea** (or run `python -m ta2 check <words>`). If an idea is listed, it has been tested,
with the variations named below, on TSX 60 daily 2000-2015 (IS) and 2016-Oct 2024 (OOS), often also US top-100
and the (now spent) Nov 2024-Oct 2026 holdout. Same rules as ta2/config.py: 0.12%/side, 0.10% stop slip, 5 random twins per trade,
week-block bootstrap, Romano-Wolf luck correction. A re-test is only worth it with a genuinely NEW rule, a NEW market,
or NEW (forward) data.

Every graded config (79,310 rows: name = dials|exit|side|entry|stop buffer, with n / win / avgR / edge vs random / p for IS and OOS)
is in `all_configs_tested.csv.gz` next to this file.

Kept strategies (code in ta2/strategies): S53 (strong), S55 (strong), S56 (weak), S31 (weak), S54 (weak), S07X (weak), S14X (weak), S45 (protection), S43 (weak), S64 (weak).

## Patterns learned (apply to every new idea)
1. Shorts lost in every strategy on TSX/US large caps -> long-only by default.
2. Most 'profitable' long rules are market drift + survivorship: random entries with the same stop/exit earn the same. Always read 'edge vs random', not avgR.
3. High win rate != edge (S78 69% wins, ~0R; 17 strategies with >51% win rate all matched by random entries on US).
4. Several entries have real timing (S07, S14, S78) but fixed stop/target exits kill it; signal-based / trailing exits helped (S07X, S14X, S53, S55, S56).
5. Market regime / trend / momentum / sector filters FLIP between 2000-15 and 2016-26 (grinding bears vs V-shaped dips): not stable rules.
6. Nothing on the signal day (volume, RSI, ATR, stop width, MA distance) separates future S53 winners from losers.
7. Portfolio construction matters more than entry tweaks: a 10-slot cap skipped the better half of S53 signals.
8. 'Beats the index' was never found: every edge here is timing vs random entries, or smaller drawdowns at similar/lower return.

## Simulations already run on the kept strategies (do not repeat without new data)
| Test | What was tried | Result |
|---|---|---|
| S53 settings plateau | MACD fast 10/12/14 x slow 21/26/31 x signal 7/9/11 (27) | all 27 positive IS+OOS, beat random, OOS p<.05: broad plateau, 12/26/9 mid-cell |
| S53 multiple-testing haircut | N=59,506 configs | IS t 3.88 fails harsh bar; OOS 3.35, full-period 5.19 clear it |
| S53 per-year / Monte Carlo | 2000-2026, 3-month blocks | +avgR 19/27 yrs; loses in 2002/08/11/15/18/22; MC median DD -32% vs XIU -37% |
| S53 tweaks | XIU>200d regime, 3-ATR trail, T-bill cash, +S14X combo | regime overfits (OOS -2.7%/yr), trail worse, cash +0.2-0.8%/yr mechanical, combo TSX-only -> base kept |
| S53 capacity | 1%x10 / 0.5%x20 / 0.33%x30 / 0.25%x40, same-day order random/deepest/low-vol | 0.33%x30 low-vol best (live rule); fails US IS |
| S53 weekly bars | same rules on W-FRI bars | TSX edge only 2000-15; US beats random 3/3; portfolio 2.5-3.6%/yr -> fails |
| S53 exit on the index | hold XIU/SPY, exit on hist<0, re-enter on S53 entry or hist>0 | fails: 2.6%/yr vs 8.3% hold (exit is not an edge alone) |
| S53 market trend (day/week/month, choppiness) | state at signal close | flips by era -> no filter |
| S53 sector trend + momentum (3/6/12-1 mo, sector, market) | quintiles set on IS | flips (2016-20 weakest stocks best) -> no filter |
| S53 reverse-engineer winners | volume, RSI, ATR%, stop%, MA dist, 52w high, signals/day | no signal-day filter holds; top 10% trades = +1,887R of +684R total |
| S53 $250 / 3-5 stock versions | 1-5 stock sizing, 200 orderings | luck-driven; 1-stock range -13% to +106%; as designed best |
| S53 on crypto | BTC 2014-26 (74 trades), ETH 2017-26 | BTC beats random every period, none significant; ETH fails -> fails |
| S53 weekly-direction filter (as taught) | weekly MACD direction gate | HURTS (as taught/as traded ~0 skill) |
| Winning-strategy search (~45 configs) | capacity, monthly factors (Faber, low-vol, momentum), vol-target+trend, dual momentum, monkey check, D1 blend | nothing beat B&H in all windows + holdout; D1 7.5%/yr -21% DD vs 8.3% -52% (TSX full) |
| Ensemble W2_C1 | S53+S55+S56+S45, inverse-vol, monthly rebalance, kill rule, T-bill cash | passes MAR rule all 4 windows, earns much less than index (3.9-6.8%/yr) |
| Win rate >51% list | 2,244 configs / 17 strategies | win rates repeat on US but random does as well (0 significant) |
| Phase 1 kit (tsxta) | trend_breakout, four_week, golden_cross, rsi_pullback, rsi_oversold per stock vs B&H | B&H beat every rule on >90% of stocks; trend rules cut DD only |
| S64/S68 calendar | Sept weakness, Sep-Feb corrections, days 1-10, sell in May, deposit timing | skip-September kept (weak); rest rejected |

## Strategy by strategy

### S01 - 50/150 SMA cross with slope filter (Adam Khoo trend rule)  [REJECTED]
- Sources: Adam Khoo (12 refs). Taught on: Indices (Dow, STI, S&P), US stocks, ETFs incl. gold/bonds/commodities and inverse ETFs
- Rule: 50-day SMA crosses above the 150-day SMA
- Ladder: 1) base cross -> 2) both SMAs flat or rising at the cross (no signal if the 150 still slopes down) -> 3) exit only when the 50 crosses below the 150 AND neither slopes up -> 4) optional: 4 consecutive lower highs confirm the top (FcuimE_LnqQ) -> 5) skip signals right after a parabolic/sudden drop (GwNx9bU5sUE) -> 6) apply to the index as a market-regime switch for stock longs
- Verdict: No edge as a stock signal (all long configs beat random IS, OOS edge -0.5%/trade; returns = owning today's survivors). As an XIU regime switch it cut drawdown in 2000-15 (-23% vs -52%) but not 2016-24 (2020 fell too fast). '>90% accuracy' claim: 55%/51%.
- S01: 2,160 configs graded. Funnel (main fees): 2160 -> 2160 -> 1080 -> 1080 -> 1080 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: pair: 40/120, 40/150, 40/200, 50/120, 50/150, 50/200, 60/120, 60/150, 60/200; entry_rule: plain, slopeN10thr-0.1%, slopeN10thr0%, slopeN10thr0.1%, slopeN20thr-0.1%, slopeN20thr0%, slopeN20thr0.1%, slopeN5thr-0.1%, slopeN5thr0%, slopeN5thr0.1%; exit: exit=either_down, exit=neither_up, exit=plain; crash: crash=0, crash=1; entry: close, next_open

### S02 - 20/40 EMA short-term trend cross  [REJECTED]
- Sources: Adam Khoo (5 refs). Taught on: US stocks and S&P 500
- Rule: 20 EMA crosses above the 40 EMA
- Ladder: 1) base cross -> 2) price structure higher high + higher low (owipUd-xyy0) -> 3) price breaks the downtrend line (owipUd-xyy0) -> 4) medium-term 50/150 agrees (GU8ft9qH74I)
- Verdict: No edge: long configs 99% profitable but median edge +0.04R = market drift.
- S02: 768 configs graded. Funnel (main fees): 768 -> 636 -> 376 -> 266 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: fast: 10, 20, 30; slow: 30, 40, 50; confirmation: medium, none, structure, structure+medium; target: 2R, 3R, reverse_cross; entry: close, next_open; buf: 0.1, 0.5
  - as taught (20/40, pattern-low stop, reverse cross) (long): IS 1056 tr, +0.22R, edge +0.12; OOS 783 tr, +0.13R, edge +0.11
  - as traded (20/40, 2R, next open) (long): IS 1033 tr, +0.14R, edge +0.01; OOS 773 tr, +0.16R, edge +0.07
  - True edge, skill vs random twins (S02):
    - IS pick 1: fast=10|slow=50|confirmation=medium|reverse_cross|L|next_open|buf0.5: TSX IS +7 R/yr (p 0.00); TSX OOS -0 R/yr (p 0.54)
    - IS pick 2: fast=20|slow=30|confirmation=medium|reverse_cross|L|close|buf0.5: TSX IS +7 R/yr (p 0.00); TSX OOS +0 R/yr (p 0.46)
    - IS pick 3: fast=20|slow=30|confirmation=medium|reverse_cross|L|close|buf0.1: TSX IS +8 R/yr (p 0.00); TSX OOS +2 R/yr (p 0.21)
    - as taught (20/40, pattern-low stop, reverse cross): TSX IS +8 R/yr (p 0.03); TSX OOS +10 R/yr (p 0.04)
    - as traded (20/40, 2R, next open): TSX IS +1 R/yr (p 0.40); TSX OOS +6 R/yr (p 0.14)

### S03 - 200-day MA regime (long above, sell rallies below; failed-retest exit)  [REJECTED]
- Sources: Adam Khoo, Booming Bulls (5 refs). Taught on: Nifty/Indian stocks; S&P 500 (Adam Khoo)
- Rule: Daily close above (long allowed) or below (longs off / sell rallies) the 200-day MA
- Ladder: 1) base side of 200 -> 2) 200 MA itself sloping up (owipUd-xyy0, UUaq0Y3Rfrg) -> 3) RSI(14) > 50 for longs (H6D0mWUda64) -> 4) exit/short when price breaks below the 200, retests it from below and is rejected (H6D0mWUda64) -> 5) used as a filter on other entries
- Verdict: No edge: long profitable 18% IS / 40% OOS, median avgR -0.14/-0.03R.
- S03: 5,184 configs graded. Funnel (main fees): 5184 -> 3375 -> 336 -> 235 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: ma: EMA, SMA; length: 150, 200, 250; trigger: cross, retest; retest_window: 10.0, 20.0, 5.0; rsi: 50.0, 60.0; slope: 20.0, 50.0; target: 1.5R, 2R, 3R; entry: close, next_open; buf: 0.1, 0.5, 1.0
  - as taught (daily SMA200 cross, RSI50, close proxy, fixed 2R) (long): IS 467 tr, -0.32R, edge -0.10; OOS 351 tr, -0.16R, edge +0.07
  - as traded (EMA200 regime cross, next open, fixed 2R) (long): IS 643 tr, -0.27R, edge -0.17; OOS 498 tr, -0.08R, edge +0.03
  - failed retest (SMA200, within 10 bars, next open, fixed 2R) (long): IS 495 tr, -0.16R, edge -0.11; OOS 353 tr, +0.02R, edge +0.08
  - True edge, skill vs random twins (S03):
    - IS pick 1: ma=SMA|length=150|trigger=cross|retest_window=None|rsi=None|slope=50|3R|L|next_open|buf0.1: TSX IS +3 R/yr (p 0.07); TSX OOS -1 R/yr (p 0.63); US IS -5 R/yr (p 0.99); US OOS +2 R/yr (p 0.30)
    - IS pick 2: ma=SMA|length=150|trigger=cross|retest_window=None|rsi=50|slope=50|3R|L|next_open|buf0.1: TSX IS +2 R/yr (p 0.09); TSX OOS -1 R/yr (p 0.62); US IS -4 R/yr (p 0.96); US OOS +2 R/yr (p 0.24)
    - IS pick 3: ma=SMA|length=250|trigger=cross|retest_window=None|rsi=60|slope=50|2R|L|next_open|buf1.0: TSX IS +2 R/yr (p 0.09); TSX OOS -2 R/yr (p 0.92); US IS +1 R/yr (p 0.34); US OOS -0 R/yr (p 0.55)
    - as taught (daily SMA200 cross, RSI50, close proxy, fixed 2R): TSX IS -3 R/yr (p 0.88); TSX OOS +3 R/yr (p 0.24); US IS -8 R/yr (p 0.96); US OOS -0 R/yr (p 0.52)
    - as traded (EMA200 regime cross, next open, fixed 2R): TSX IS -7 R/yr (p 1.00); TSX OOS +2 R/yr (p 0.35); US IS +6 R/yr (p 0.09); US OOS +4 R/yr (p 0.30)
    - failed retest (SMA200, within 10 bars, next open, fixed 2R): TSX IS -3 R/yr (p 0.93); TSX OOS +3 R/yr (p 0.19); US IS +1 R/yr (p 0.44); US OOS +8 R/yr (p 0.04)
  - Also run: S03_US

### S04 - MA pullback/bounce buy in an uptrend (the MA the stock respects)  [REJECTED]
- Sources: Adam Khoo, Booming Bulls (7 refs). Taught on: US stocks (AK), Indian stocks (BB), large caps
- Rule: In an uptrend, price pulls back to a key moving average and closes back up (bullish candle)
- Ladder: 1) uptrend (HH/HL; 50>150) -> 2) pullback touches the MA -> 3) bullish reaction candle -> 4) for 200-DMA version: holds support 5+ days then daily close above the consolidation high (ffnjYy6HYZE) -> 5) higher-timeframe trend agrees (jjJXW2Kgjpg, zRW8nL1Sjtc)
- Verdict: No edge (best p 0.07): long ~0R; AK as taught +0.01/-0.08R; 200MA pullback +0.05/+0.08R (edge +0.02/+0.06).
- S04: 4,320 configs graded. Funnel (main fees): 4320 -> 4314 -> 1328 -> 863 -> 81 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: ma: 100, 150, 20, 200, 50; stop: low, ma; touch: x0, x1, x2; candle: green, third; trend: 50>150, none; target: 1.5R, 2R, 3R; entry: close, next_open; buf: 0.1, 0.5, 1.0
  - as taught AK (50 MA, uptrend 50>150, bullish candle, buy above its high next day, stop below swing low, 2R) (long): IS 740 tr, +0.01R, edge -0.01; OOS 449 tr, -0.08R, edge -0.03
  - as traded (50 MA, low within 1%, any green close, next open, stop below MA, 2R) (long): IS 1595 tr, -0.01R, edge +0.06; OOS 931 tr, -0.13R, edge -0.07
  - 200 MA version (uptrend, stop below MA, 2R) (long): IS 804 tr, +0.05R, edge +0.02; OOS 478 tr, +0.08R, edge +0.06
  - 20 MA version (uptrend, stop below swing low, 2R) (long): IS 1370 tr, -0.03R, edge +0.02; OOS 880 tr, -0.06R, edge +0.03
  - True edge, skill vs random twins (S04):
    - 20 MA version (uptrend, stop below swing low, 2R): TSX IS +1 R/yr (p 0.37); TSX OOS +3 R/yr (p 0.33)
    - 200 MA version (uptrend, stop below MA, 2R): TSX IS +1 R/yr (p 0.38); TSX OOS +3 R/yr (p 0.24)
    - IS pick 1: ma=200|stop=ma|touch=x2|candle=green|trend=none|1.5R|L|next_open|buf0.1: TSX IS +12 R/yr (p 0.00); TSX OOS +0 R/yr (p 0.45)
    - IS pick 2: ma=200|stop=ma|touch=x2|candle=green|trend=none|2R|L|next_open|buf0.1: TSX IS +11 R/yr (p 0.00); TSX OOS +2 R/yr (p 0.36)
    - IS pick 3: ma=150|stop=ma|touch=x2|candle=green|trend=50>150|2R|L|next_open|buf1.0: TSX IS +9 R/yr (p 0.01); TSX OOS -2 R/yr (p 0.60)
    - as taught AK (50 MA, uptrend 50>150, bullish candle, buy above its high next day, stop below swing low, 2R): TSX IS -0 R/yr (p 0.55); TSX OOS -1 R/yr (p 0.63)
    - as traded (50 MA, low within 1%, any green close, next open, stop below MA, 2R): TSX IS +6 R/yr (p 0.10); TSX OOS -8 R/yr (p 0.88)

### S05 - Adam Khoo momentum breakout system (RS>=85 + MA stack, base breakout)  [REJECTED]
- Sources: Adam Khoo (4 refs). Taught on: US stocks (TC2000 scans)
- Rule: Bullish close above a resistance level tested >=3 times (base-consolidation breakout)
- Ladder: 1) relative strength rating >= 85 (top 15% of market) -> 2) 20 EMA > 40 EMA and 50 > 150 > 200 SMA -> 3) one of 4 entries: base breakout / breakout within base (pullback high) / explosive flag (>100% in ~2 months then down-sloping flag) / MA retracement (see S06) -> 4) no open position into earnings -> 5) max 2 new trades/day, <=2 per sector
- Verdict: No edge: long 77% profitable IS -> 34% OOS, median edge -0.01/-0.10R.
- S05: 1,152 configs graded. Funnel (main fees): 1152 -> 1036 -> 794 -> 384 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: stop: atr1, atr15, atr2, atr3; touches: 2, 3, 4; rs_xiu_excess: 0.0, 0.05, 0.1, 0.2; trend: ema, none, stack; entry_rule: close_or_next_session_stop; target: 1.5R, 2R, 3R, be1_2R; entry: close, next_open; buf: 0.0
  - as taught (base-only proxy, XIU excess >=10pp, full stack, 1.5ATR, BE+1R) (long): IS 238 tr, +0.00R, edge -0.06; OOS 140 tr, +0.10R, edge +0.00
  - as traded (base-only proxy, outperform XIU, EMA20/40, 2ATR) (long): IS 886 tr, +0.10R, edge -0.03; OOS 652 tr, +0.06R, edge -0.00
  - True edge, skill vs random twins (S05):
    - IS pick 1: stop=atr1|touches=3|rs_xiu_excess=0.1|trend=ema|entry_rule=close_or_next_session_stop|2R|L|next_open|buf0.0: TSX IS +6 R/yr (p 0.00); TSX OOS +1 R/yr (p 0.27)
    - IS pick 2: stop=atr1|touches=3|rs_xiu_excess=0.1|trend=none|entry_rule=close_or_next_session_stop|2R|L|next_open|buf0.0: TSX IS +6 R/yr (p 0.00); TSX OOS +2 R/yr (p 0.22)
    - IS pick 3: stop=atr1|touches=3|rs_xiu_excess=0.1|trend=ema|entry_rule=close_or_next_session_stop|1.5R|L|next_open|buf0.0: TSX IS +4 R/yr (p 0.01); TSX OOS +0 R/yr (p 0.41)
    - as taught (base-only proxy, XIU excess >=10pp, full stack, 1.5ATR, BE+1R): TSX IS -1 R/yr (p 0.69); TSX OOS +0 R/yr (p 0.50)
    - as traded (base-only proxy, outperform XIU, EMA20/40, 2ATR): TSX IS -2 R/yr (p 0.69); TSX OOS -0 R/yr (p 0.49)

### S06 - Trend retracement bounce with confluence (Adam Khoo "bounce"/EMA-bounce system)  [REJECTED]
- Sources: Adam Khoo (5 refs). Taught on: US stocks
- Rule: In an uptrend, price pulls back into "double support" (a tested MA + horizontal support) and prints a bullish candle
- Ladder: 1) index uptrending -> 2) stock MA stack 20EMA>40EMA>50>150, price>200, all rising -> 3) pullback to double support -> 4) oscillator oversold (Williams %R or stochastic <20) -> 5) Fib 61.8% coincides (K8xHGw4N1sQ example) -> 6) confluence count >= 3 (adOETTJoj_k)
- Verdict: AK '+368R / 567 trades' not reproduced: setup too rare on TSX 60 (median 3 trades/config); configs 100% profitable IS -> 8% OOS.
- S06: 1,188 configs graded. Funnel (main fees): 1188 -> 90 -> 54 -> 44 -> 28 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: target: 1.5R, 2R, 3R; entry: close, next_open; buf: 0.5, 1.0, 1.5; variant: base, ladder_ds2, stack
  - as taught (long): IS 22 tr, +0.33R, edge +0.08; OOS 24 tr, -0.27R, edge -0.73
  - as traded (long): IS 1 tr, +0.32R, edge +0.55
  - True edge, skill vs random twins (S06):
    - as taught: TSX IS +0 R/yr (p 0.40); TSX OOS -2 R/yr (p 1.00)
    - as traded: TSX IS +0 R/yr (p 0.00)

### S07 - Slingshot mean reversion (lower BB + stochastic oversold + support + bullish candle)  [REJECTED]
- Sources: Adam Khoo (7 refs). Taught on: US stocks, S&P (as a timing filter for adding to holdings)
- Rule: Price pierces the lower Bollinger Band (20,2) with stochastic < 20 at a strong support
- Ladder: 1) base: lower-BB pierce + stoch<20 -> 2) at strong support (tested MA, 3-touch horizontal, double-bottom take-out-stop, or Fib level) -> 3) bullish confirmation candle (pin/engulfing/full body) -> 4) act on stochastic crossing back above 20 ("2 of 3" rule, r2aCcKWXplI) -> 5) uptrend context (JpeRll7tu48 version) ; mirror short at upper BB + stoch>80 + double top (q9DnT0R_td4)
- Verdict: Timing beats random (3 configs, RW p .000) but trades only break even after fixed exits/costs. Entry re-used in S07X (KEPT, weak).
- S07: 3,888 configs graded. Funnel (main fees): 3888 -> 3573 -> 1155 -> 1076 -> 140 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: bb_sd: 2.0, 2.5; stoch: 10, 20, 30; trend: SMA50>SMA150, close>SMA200, none; required: 2 of 3, 3 of 3, 3 of 3 + candle; trigger: buy the close, next-day stop above high; target: 1.5R, 2R, opp; entry: close, next_open; buf: 0.1, 0.5, 1.0
  - as taught (all 4: BB, stoch<20, support, candle; buy-stop above high; 2R) (long): IS 806 tr, -0.06R, edge -0.03; OOS 552 tr, -0.05R, edge -0.01
  - as traded (2 of 3, buy the close, 2R) (long): IS 4131 tr, -0.20R, edge +0.08; OOS 2764 tr, -0.33R, edge -0.06
  - uptrend version (close>SMA200) (long): IS 2332 tr, -0.19R, edge +0.08; OOS 1548 tr, -0.33R, edge -0.09
  - True edge, skill vs random twins (S07):
    - IS pick 1: bb_sd=2.5|stoch=30|trend=none|required=2 of 3|trigger=next-day stop above high|opp|L|close|buf0.1: TSX IS +21 R/yr (p 0.00); TSX OOS +12 R/yr (p 0.02)
    - IS pick 2: bb_sd=2|stoch=30|trend=none|required=2 of 3|trigger=next-day stop above high|opp|L|close|buf0.1: TSX IS +16 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.16)
    - IS pick 3: bb_sd=2.5|stoch=20|trend=none|required=2 of 3|trigger=next-day stop above high|opp|L|close|buf0.1: TSX IS +17 R/yr (p 0.00); TSX OOS +7 R/yr (p 0.10)
    - as taught (all 4: BB, stoch<20, support, candle; buy-stop above high; 2R): TSX IS -1 R/yr (p 0.64); TSX OOS -1 R/yr (p 0.56)
    - as traded (2 of 3, buy the close, 2R): TSX IS +20 R/yr (p 0.01); TSX OOS -19 R/yr (p 0.89)
    - uptrend version (close>SMA200): TSX IS +11 R/yr (p 0.04); TSX OOS -15 R/yr (p 0.93)
- S07X: 432 configs graded. Funnel (main fees): 432 -> 432 -> 149 -> 142 -> 5 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: setup: as taught, as traded, confirm_sd2.5_st20, confirm_sd2.5_st30, confirm_sd2_st20, confirm_sd2_st30; bb_sd: 2.0, 2.5; stoch: 20.0, 30.0; required: 2 of 3; trigger: next-day stop above high; target: 2R, be1_2R, be1_3R, half1R_trail2atr, time10, time5, trail2atr, trail3atr, trail_ma20; entry: close, next_open; buf: 0.1, 0.5
  - as taught | 2R (long): IS 802 tr, -0.04R, edge -0.05; OOS 552 tr, -0.03R, edge -0.01
  - as taught | be1_2R (long): IS 805 tr, -0.12R, edge -0.07; OOS 561 tr, -0.10R, edge -0.03
  - as taught | be1_3R (long): IS 804 tr, -0.09R, edge -0.08; OOS 557 tr, -0.04R, edge -0.00
  - as taught | trail2atr (long): IS 808 tr, +0.06R, edge +0.10; OOS 567 tr, +0.03R, edge +0.08
  - as taught | trail3atr (long): IS 808 tr, +0.15R, edge +0.15; OOS 563 tr, +0.28R, edge +0.29
  - as taught | trail_ma20 (long): IS 809 tr, -0.14R, edge -0.08; OOS 567 tr, -0.06R, edge -0.00
  - as taught | half1R_trail2atr (long): IS 808 tr, -0.04R, edge +0.03; OOS 567 tr, -0.06R, edge +0.01
  - as taught | time5 (long): IS 809 tr, -0.10R, edge -0.02; OOS 567 tr, -0.12R, edge -0.05
  - as taught | time10 (long): IS 809 tr, -0.04R, edge -0.01; OOS 567 tr, -0.03R, edge -0.01
  - as traded | 2R (long): IS 4122 tr, -0.20R, edge +0.05; OOS 2753 tr, -0.32R, edge -0.04
  - as traded | be1_2R (long): IS 4218 tr, -0.23R, edge +0.05; OOS 2802 tr, -0.34R, edge -0.03
  - as traded | be1_3R (long): IS 4177 tr, -0.18R, edge +0.07; OOS 2778 tr, -0.30R, edge -0.03
  - True edge, skill vs random twins (S07X):
    - IS pick 1: setup=confirm_sd2.5_st30|bb_sd=2.5|stoch=30|required=2 of 3|trigger=next-day stop above high|half1R_trail2atr|L|close|buf0.1: TSX IS +23 R/yr (p 0.00); TSX OOS +12 R/yr (p 0.07); US IS +29 R/yr (p 0.00); US OOS +11 R/yr (p 0.19)
    - IS pick 2: setup=confirm_sd2.5_st30|bb_sd=2.5|stoch=30|required=2 of 3|trigger=next-day stop above high|trail3atr|L|close|buf0.5: TSX IS +32 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.30); US IS +23 R/yr (p 0.06); US OOS -3 R/yr (p 0.56)
    - IS pick 3: setup=confirm_sd2.5_st30|bb_sd=2.5|stoch=30|required=2 of 3|trigger=next-day stop above high|2R|L|close|buf0.1: TSX IS +21 R/yr (p 0.00); TSX OOS +15 R/yr (p 0.06); US IS +27 R/yr (p 0.01); US OOS +30 R/yr (p 0.02)
    - as taught | 2R: TSX IS -2 R/yr (p 0.75); TSX OOS -0 R/yr (p 0.52); US IS +3 R/yr (p 0.30); US OOS -4 R/yr (p 0.66)
    - as taught | be1_2R: TSX IS -4 R/yr (p 0.89); TSX OOS -2 R/yr (p 0.66); US IS +3 R/yr (p 0.26); US OOS -4 R/yr (p 0.66)
    - as taught | be1_3R: TSX IS -4 R/yr (p 0.88); TSX OOS -0 R/yr (p 0.50); US IS +0 R/yr (p 0.48); US OOS -2 R/yr (p 0.59)
    - as taught | half1R_trail2atr: TSX IS +2 R/yr (p 0.28); TSX OOS +1 R/yr (p 0.42); US IS +2 R/yr (p 0.35); US OOS -0 R/yr (p 0.51)
    - as taught | time10: TSX IS -0 R/yr (p 0.51); TSX OOS -1 R/yr (p 0.54); US IS -2 R/yr (p 0.65); US OOS -7 R/yr (p 0.74)
    - as taught | time5: TSX IS -1 R/yr (p 0.61); TSX OOS -3 R/yr (p 0.71); US IS +2 R/yr (p 0.33); US OOS -6 R/yr (p 0.78)
    - as taught | trail2atr: TSX IS +5 R/yr (p 0.12); TSX OOS +5 R/yr (p 0.23); US IS +3 R/yr (p 0.34); US OOS -1 R/yr (p 0.54)

### S08 - Fibonacci golden-zone pullback (50-61.8%) with a trigger  [REJECTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (12 refs). Taught on: Forex, gold, crude, NASDAQ (BB); S&P, US stocks (AK); gold (PoS)
- Rule: After an impulse leg, price retraces into the 50-61.8% Fibonacci zone of that leg
- Ladder: 1) trend defined (2+ higher highs/lows, MAs in sequence) -> 2) retracement into 50-61.8% (skip 38.2 and 78.6, 3gj7MbZ0vHs) -> 3) trigger candle (pin bar/engulfing, AigD5Rqoobg) or sweep/double bottom/FVG on lower TF -> 4) zone lines up with a prior level or MA (qLeA6k-UcuQ, mVNOU9O5vkE) -> 5) higher low holds (CkrNtbtFev4)
- Verdict: No edge (best p 0.89). The 50-61.8% 'golden zone' was the WEAKEST zone. Fib alone long -0.20R.
- S08: 6,912 configs graded. Funnel (main fees): 6912 -> 5416 -> 2384 -> 1147 -> 588 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: swing: 3, 5; min_leg: 10, 5; zone: 38.2-50, 38.2-61.8, 50-61.8; trigger: engulfing, pin, prior_high; stop: candle, swing; extension: 1.0, 1.618; target: 1.5R, 2R, 3R, opp; entry: close, next_open; buf: 0.1, 0.5, 1.0
  - as taught (long): IS 3 tr, -0.68R, edge -0.11; OOS 1 tr, -1.10R, edge -1.39
  - as traded (long): IS 95 tr, -0.10R, edge -0.05; OOS 51 tr, -0.37R, edge -0.35
  - Fib alone (no trigger) (long): IS 1937 tr, -0.20R, edge -0.01; OOS 1058 tr, -0.23R, edge -0.04
  - 1.618 extension (long): IS 94 tr, -0.35R, edge -0.37; OOS 51 tr, +0.20R, edge +0.09
  - impulse-start stop (long): IS 94 tr, +0.11R, edge -0.04; OOS 54 tr, -0.20R, edge -0.35
  - True edge, skill vs random twins (S08):
    - 1.618 extension: TSX IS -2 R/yr (p 0.99); TSX OOS +1 R/yr (p 0.39); US IS -5 R/yr (p 1.00); US OOS -4 R/yr (p 0.99)
    - Fib alone (no trigger): TSX IS -1 R/yr (p 0.59); TSX OOS -5 R/yr (p 0.79); US IS +14 R/yr (p 0.04); US OOS +12 R/yr (p 0.13)
    - IS pick 1: swing=3|min_leg=5|zone=38.2-50|trigger=pin|stop=swing|extension=1.0|1.5R|L|next_open|buf0.5: TSX IS +2 R/yr (p 0.00); TSX OOS +1 R/yr (p 0.20); US IS -1 R/yr (p 0.66); US OOS +0 R/yr (p 0.47)
    - IS pick 2: swing=3|min_leg=5|zone=38.2-50|trigger=pin|stop=swing|extension=1.0|opp|L|next_open|buf0.5: TSX IS +2 R/yr (p 0.00); TSX OOS +1 R/yr (p 0.22); US IS +0 R/yr (p 0.34); US OOS -0 R/yr (p 0.57)
    - IS pick 3: swing=3|min_leg=5|zone=38.2-50|trigger=engulfing|stop=candle|extension=1.0|2R|L|next_open|buf0.5: TSX IS +3 R/yr (p 0.01); TSX OOS +4 R/yr (p 0.02); US IS -2 R/yr (p 0.85); US OOS -3 R/yr (p 0.92)
    - as taught: TSX IS -0 R/yr (p 0.71); TSX OOS -0 R/yr (p 1.00); US IS +0 R/yr (p 0.37); US OOS -0 R/yr (p 1.00)
    - as traded: TSX IS -0 R/yr (p 0.64); TSX OOS -2 R/yr (p 0.92); US IS -0 R/yr (p 0.54); US OOS -1 R/yr (p 0.76)
    - impulse-start stop: TSX IS -0 R/yr (p 0.62); TSX OOS -2 R/yr (p 0.97); US IS -1 R/yr (p 0.84); US OOS -2 R/yr (p 0.91)
  - Also run: S08_US

### S09 - Breakout after consolidation (base/box/range breakout with quality filters)  [REJECTED]
- Sources: Booming Bulls, Power of Stocks (27 refs). Taught on: Indian stocks/indices (BB, PoS), forex (BB), US stocks (AK)
- Rule: Close above the high of a consolidation range (box) after price has spent time near the level
- Ladder: 1) base: close beyond range high -> 2) range is tight (stocks ~1-5%, UNXxttTXD3A; <1% over 3-4 days, lPLHKKk5GAs) -> 3) level tested before (>=3 touches, BB/AK; PoS says 3+ touches = weak level that breaks) -> 4) time spent near the level before the break (xBrTpbzQ_kM, hrGUwS58o-I) -> 5) breakout volume > 10-day average (Varsity/Murphy) -> 6) ADX(14) > 20 and rising (Pw74EDSHYSw) -> 7) no gap-thro
- Verdict: No edge. One low-fee config passed the luck test IS (+0.24R) then went -0.07R OOS (lucky fit). Watch note: next-day confirmation +0.03/+0.02R vs random.
- S09: 1,728 configs graded. Funnel (main fees): 1728 -> 1269 -> 434 -> 332 -> 82 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: lookback: 10, 20, 5, 60; tight: 10, 15, 2, 5; touches: 1, 2, 3; target: 1.5R, 2R, opp; entry: close, next_open; buf: 0.1, 0.5, 1.0
  - as taught (20d box <=5%, 3 touches, near, vol, ADX up, no gap, room 2R; enter at close) (long): IS 17 tr, +0.62R, edge +0.68; OOS 14 tr, -0.37R, edge +0.11
  - as traded (20d box <=10%, 2 touches, next open) (long): IS 2286 tr, +0.00R, edge +0.07; OOS 1725 tr, -0.09R, edge -0.03
  - as traded, stop below range (long): IS 1716 tr, +0.19R, edge +0.05; OOS 1261 tr, +0.08R, edge -0.03
  - as traded, box-height target (long): IS 2232 tr, +0.10R, edge +0.16; OOS 1650 tr, +0.03R, edge +0.04
  - 3-4 day box (5d <=2%) (long): IS 1419 tr, +0.07R, edge +0.12; OOS 1260 tr, -0.08R, edge +0.04
  - True edge, skill vs random twins (S09):
    - 3-4 day box (5d <=2%): TSX IS +11 R/yr (p 0.01); TSX OOS +6 R/yr (p 0.26)
    - IS pick 1: lookback=20|tight=5|touches=2|1.5R|L|next_open|buf0.1: TSX IS +10 R/yr (p 0.00); TSX OOS -7 R/yr (p 0.95)
    - IS pick 2: lookback=5|tight=2|touches=1|2R|L|next_open|buf0.5: TSX IS +18 R/yr (p 0.00); TSX OOS +4 R/yr (p 0.31)
    - IS pick 3: lookback=5|tight=2|touches=1|2R|L|close|buf0.5: TSX IS +19 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.29)
    - as taught (20d box <=5%, 3 touches, near, vol, ADX up, no gap, room 2R; enter at close): TSX IS +1 R/yr (p 0.04); TSX OOS +0 R/yr (p 0.41)
    - as traded (20d box <=10%, 2 touches, next open): TSX IS +10 R/yr (p 0.05); TSX OOS -6 R/yr (p 0.71)
    - as traded, box-height target: TSX IS +22 R/yr (p 0.01); TSX OOS +7 R/yr (p 0.29)
    - as traded, stop below range: TSX IS +6 R/yr (p 0.06); TSX OOS -4 R/yr (p 0.77)

### S10 - Channel breakout trend systems: 4-week rule [M] and Donchian/Keltner [DA]  [REJECTED]
- Sources: TA books/papers [M] ch 9 [claude/technical-analysis-notes.md]; TA books/papers [DA] Zarattini & Antonacci 2025 [claude/t (3 refs). Taught on: US industries/sector ETFs ([DA]); futures ([M] evidence)
- Rule: Close above the prior 4-week (or 20-day Donchian/Keltner) high
- Ladder: 1) base channel break -> 2) [DA] lower of Donchian-20 high and Keltner upper -> 3) ratcheting exit at higher of 40-day Donchian low / Keltner lower -> 4) volatility sizing (1.5%/N)/14d vol, exposure cap 200% -> 5) apply to sector/industry ETFs or index rather than single stocks
- Verdict: No edge: long median edge -0.02/-0.02R; 4-week rule as taught $10k -> $6,090 / $8,350.
- S10: 864 configs graded. Funnel (main fees): 864 -> 864 -> 296 -> 155 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: channel: combined, donchian, keltner; entry_days: 10, 20, 55; gate: adx20, none, trend200; target: 2R, trail2atr, trail3atr, trail_ma20; entry: close, next_open; buf: 0.1, 0.5
  - as taught: four-week daily proxy (long): IS 3066 tr, -0.01R, edge -0.01; OOS 2098 tr, -0.01R, edge -0.03
  - as traded: combined channel (long): IS 2731 tr, +0.05R, edge -0.01; OOS 1843 tr, +0.01R, edge -0.04
  - True edge, skill vs random twins (S10):
    - IS pick 1: channel=combined|entry_days=55|gate=none|trail_ma20|L|next_open|buf0.5: TSX IS +8 R/yr (p 0.00); TSX OOS +8 R/yr (p 0.02)
    - IS pick 2: channel=combined|entry_days=20|gate=none|trail_ma20|L|next_open|buf0.1: TSX IS +11 R/yr (p 0.00); TSX OOS +4 R/yr (p 0.17)
    - IS pick 3: channel=keltner|entry_days=55|gate=none|trail_ma20|L|next_open|buf0.5: TSX IS +7 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.10)
    - as taught: four-week daily proxy: TSX IS -3 R/yr (p 0.89); TSX OOS -7 R/yr (p 0.97)
    - as traded: combined channel: TSX IS -1 R/yr (p 0.65); TSX OOS -8 R/yr (p 0.95)

### S11 - Breakout-retest (role reversal: broken resistance holds as support)  [REJECTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (11 refs). Taught on: Gold, Nifty, Indian stocks, forex
- Rule: After a breakout, price returns to the broken level and holds it with a reaction candle
- Ladder: 1) prior breakout of a valid level -> 2) first retest only (LZ5FhBFy-9s: first retest strongest) -> 3) reaction/rejection candle at the level -> 4) level qualified by a >=5-10% reaction for stocks (WXZ2ZAWx2uU) -> 5) "proof of concept": retest after a completed pattern (Ezlqgr74DC0) -> 6) HTF level + LTF trigger (YKk2WmtZNS0)
- Verdict: No edge, worst of batch 1: 0 configs PF>=1.3; as taught 55% wins but -0.18R.
- S11: 2,592 configs graded. Funnel (main fees): 2592 -> 2592 -> 233 -> 33 -> 0 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: stop: level, swing; dial_window: 10, 20, 5; tol: 0.5, 1.0, 2.0; reaction: 10, 3, 5, any; target: 1.5R, 2R, opp; entry: close, next_open; buf: 0.1, 0.5, 1.0
  - as taught (first retest, level reacted >=5%, strong candle, target prior swing high, stop below retest low, at close) (long): IS 1130 tr, -0.18R, edge -0.05; OOS 724 tr, -0.17R, edge +0.01
  - as traded (retest within 10 bars, low within 1%, 2R, next open) (long): IS 3981 tr, -0.06R, edge -0.01; OOS 2781 tr, -0.14R, edge -0.04
  - stop under the level (long): IS 3969 tr, -0.06R, edge -0.02; OOS 2747 tr, -0.10R, edge -0.06
  - True edge, skill vs random twins (S11):
    - IS pick 1: stop=swing|window=20|tol=2|reaction=any|opp|L|next_open|buf0.1: TSX IS +8 R/yr (p 0.02); TSX OOS +7 R/yr (p 0.08)
    - IS pick 2: stop=swing|window=20|tol=1|reaction=any|opp|L|next_open|buf0.1: TSX IS +7 R/yr (p 0.02); TSX OOS +9 R/yr (p 0.03)
    - IS pick 3: stop=swing|window=5|tol=1|reaction=3|opp|L|next_open|buf1.0: TSX IS +4 R/yr (p 0.03); TSX OOS +4 R/yr (p 0.08)
    - as taught (first retest, level reacted >=5%, strong candle, target prior swing high, stop below retest low, at close): TSX IS -3 R/yr (p 0.93); TSX OOS +1 R/yr (p 0.42)
    - as traded (retest within 10 bars, low within 1%, 2R, next open): TSX IS -2 R/yr (p 0.62); TSX OOS -13 R/yr (p 0.86)
    - stop under the level: TSX IS -5 R/yr (p 0.75); TSX OOS -18 R/yr (p 0.93)

### S12 - Opening-range breakout (first 5/15-min candle)  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (13 refs). Taught on: Nifty, Indian stocks, US stocks (US open)
- Rule: Price breaks the high/low of the first 5-min (or 15-min) candle of the session
- Ladder: 1) base ORB break on a candle close with real body -> 2) range < 1% of price (4iPEKSo_vwY, T_VlPXyqj0U) -> 3) not all opening candles big (one big + two small best) -> 4) entries only in first ~1-2 hours -> 5) ADX rising (Pw74EDSHYSw) -> 6) diversify across 5-6 uncorrelated names at 1/6 risk each (acNnFSjyOTw) -> 7) pre-open top-3 by traded value (9lcrhsg98XE); skip price < Rs100 or range > 2% (Yv
- Why not tested: Not tested (needs intraday bars). | Type: Entry. Partly taught on Indian/forex/gold markets - check transfer. TSX open 9:30 ET. TradingView intraday history may allow a limited test (see open questions). | Sources: 12 videos/docs from Booming Bulls, Power of Stocks. Ease of coding 3/3.

### S13 - Inside-bar (mother/baby candle) breakout  [REJECTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (5 refs). Taught on: Nifty 50 stocks, Bank Nifty (PoS); US30, NAS100, gold (BB)
- Rule: Price breaks out of the range of a large "mother" candle after one or more inside ("baby") candles
- Ladder: 1) mother candle + >=1 inside candle (>=2 for kakFchv-ylo) -> 2) enter on baby break, add on mother break (42J_foitsdI) -> 3) direction = prior trend / after a big fall sell side -> 4) wick filter: cancel a side if a wick poked >X outside the box first (kakFchv-ylo) -> 5) trigger candle opposite wick <=30% (Lb4yel3nCws) -> 6) liquid top-15 watchlist only
- Verdict: No edge: one config passed IS, 0 OOS; as traded +0.07R both windows but edge ~0.
- S13: 1,152 configs graded. Funnel (main fees): 1152 -> 1152 -> 401 -> 309 -> 1 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: reference: baby, mother; inside: 1, 2; trend: none, trend200, trend50150; wick: clean, none, wick30; target: 1.5R, 1R, 2R, opp; entry: close, next_open; buf: 0.1, 0.5
  - as taught (daily adaptation) (long): IS 9293 tr, -0.05R, edge +0.02; OOS 5715 tr, -0.06R, edge +0.02
  - as traded (daily mother close) (long): IS 6194 tr, +0.07R, edge -0.00; OOS 3941 tr, +0.07R, edge +0.01
  - True edge, skill vs random twins (S13):
    - IS pick 1: reference=baby|inside=2|trend=none|wick=wick30|1R|L|close|buf0.1: TSX IS +18 R/yr (p 0.00); TSX OOS +4 R/yr (p 0.22)
    - IS pick 2: reference=baby|inside=2|trend=none|wick=none|1R|L|next_open|buf0.1: TSX IS +16 R/yr (p 0.00); TSX OOS +2 R/yr (p 0.38)
    - IS pick 3: reference=mother|inside=2|trend=none|wick=clean|opp|L|next_open|buf0.1: TSX IS +12 R/yr (p 0.00); TSX OOS +4 R/yr (p 0.22)
    - as taught (daily adaptation): TSX IS +9 R/yr (p 0.20); TSX OOS +15 R/yr (p 0.16)
    - as traded (daily mother close): TSX IS -1 R/yr (p 0.52); TSX OOS +3 R/yr (p 0.42)

### S14 - Double top/bottom (M/W) and head & shoulders - neckline-break entry  [REJECTED]
- Sources: Booming Bulls, Power of Stocks (13 refs). Taught on: Indian stocks, Nifty, forex, gold
- Rule: Close through the neckline (middle swing) of an M/W or H&S pattern
- Ladder: 1) prior established trend into the pattern (nDKqroFfbSI) -> 2) neckline break with a power candle (check body% vs wick%) -> 3) pattern at an HTF level: daily S/R or 60m last-5-day S/R (4fXJRcCfWqA) -> 4) clean shape: V-recovery between tops, pattern at structure extreme not mid-range (VeRFSaOj6S4, a-VAXIg4gZc) -> 5) in direction of the post-range trend (T3AyXqau_QA) -> 6) volume expands on break 
- Verdict: No edge (closest of batch 1, best p 0.08): W bottom lows within 1% +0.31/+0.15R. Shorts (M) lose everywhere. Entry re-used in S14X (KEPT, weak).
- S14: 2,592 configs graded. Funnel (main fees): 2592 -> 2313 -> 813 -> 554 -> 388 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: stop: candle, leg, top; equality: 1, 2, 3, 5; spacing: 10, 20; trend: 10, 20, none; target: 1.5R, 2R, opp; entry: close, next_open; buf: 0.1, 0.5, 1.0
  - as taught BB/PoS (2nd-leg stop, tops within 3%, prior trend, power candle, 2R, enter at break close) (long): IS 559 tr, +0.20R, edge +0.09; OOS 373 tr, +0.08R, edge -0.06
  - as traded (pattern-extreme stop, within 3%, pattern-height target, next open) (long): IS 1959 tr, +0.12R, edge +0.04; OOS 1364 tr, +0.05R, edge -0.04
  - Murphy (>=20 bars apart, prior trend 20%, volume expands, pattern-height target) (long): IS 68 tr, -0.05R, edge -0.11; OOS 38 tr, +0.17R, edge +0.18
  - True edge, skill vs random twins (S14):
    - IS pick 1: stop=leg|equality=1|spacing=10|trend=none|2R|L|close|buf0.1: TSX IS +10 R/yr (p 0.00); TSX OOS +4 R/yr (p 0.17); US IS +2 R/yr (p 0.34); US OOS +4 R/yr (p 0.25)
    - IS pick 2: stop=top|equality=1|spacing=10|trend=none|2R|L|close|buf0.1: TSX IS +9 R/yr (p 0.00); TSX OOS +0 R/yr (p 0.49); US IS +3 R/yr (p 0.20); US OOS +3 R/yr (p 0.27)
    - IS pick 3: stop=candle|equality=1|spacing=10|trend=none|2R|L|close|buf1.0: TSX IS +12 R/yr (p 0.00); TSX OOS +3 R/yr (p 0.27); US IS +4 R/yr (p 0.23); US OOS -2 R/yr (p 0.65)
    - Murphy (>=20 bars apart, prior trend 20%, volume expands, pattern-height target): TSX IS -0 R/yr (p 0.91); TSX OOS +1 R/yr (p 0.05); US IS +0 R/yr (p 0.42); US OOS -1 R/yr (p 0.85)
    - as taught BB/PoS (2nd-leg stop, tops within 3%, prior trend, power candle, 2R, enter at break close): TSX IS +3 R/yr (p 0.09); TSX OOS -2 R/yr (p 0.75); US IS +3 R/yr (p 0.14); US OOS -6 R/yr (p 0.91)
    - as traded (pattern-extreme stop, within 3%, pattern-height target, next open): TSX IS +4 R/yr (p 0.06); TSX OOS -6 R/yr (p 0.89); US IS +2 R/yr (p 0.36); US OOS -15 R/yr (p 0.99)
  - Also run: S14_US
- S14X: 288 configs graded. Funnel (main fees): 288 -> 288 -> 271 -> 262 -> 16 -> 11  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: setup: W_eq1_sp10_candle, W_eq1_sp10_leg, W_eq1_sp10_top, W_eq1_sp20_candle, W_eq1_sp20_leg, W_eq1_sp20_top, as taught BB/PoS, as traded; equality: 1.0; spacing: 10.0, 20.0; stop: candle, leg, top; target: 2R, be1_2R, be1_3R, half1R_trail2atr, time10, time5, trail2atr, trail3atr, trail_ma20; entry: close, next_open; buf: 0.1, 0.5
  - as taught | 2R (long): IS 548 tr, +0.25R, edge +0.09; OOS 368 tr, +0.11R, edge -0.07
  - as taught | be1_2R (long): IS 551 tr, +0.16R, edge +0.04; OOS 369 tr, +0.08R, edge -0.09
  - as taught | be1_3R (long): IS 550 tr, +0.12R, edge -0.01; OOS 369 tr, +0.13R, edge -0.09
  - as taught | trail2atr (long): IS 580 tr, -0.01R, edge +0.01; OOS 395 tr, -0.06R, edge -0.11
  - as taught | trail3atr (long): IS 570 tr, +0.06R, edge +0.05; OOS 384 tr, +0.07R, edge -0.04
  - as taught | trail_ma20 (long): IS 584 tr, +0.05R, edge +0.07; OOS 390 tr, +0.05R, edge +0.05
  - as taught | half1R_trail2atr (long): IS 580 tr, +0.00R, edge +0.02; OOS 395 tr, -0.06R, edge -0.10
  - as taught | time5 (long): IS 595 tr, +0.00R, edge +0.01; OOS 399 tr, -0.05R, edge -0.03
  - as taught | time10 (long): IS 587 tr, +0.03R, edge +0.02; OOS 393 tr, -0.05R, edge -0.09
  - as traded | 2R (long): IS 1578 tr, +0.24R, edge +0.06; OOS 1125 tr, +0.12R, edge -0.05
  - as traded | be1_2R (long): IS 1604 tr, +0.23R, edge +0.06; OOS 1135 tr, +0.13R, edge -0.03
  - as traded | be1_3R (long): IS 1574 tr, +0.24R, edge +0.05; OOS 1115 tr, +0.14R, edge -0.03
  - True edge, skill vs random twins (S14X):
    - IS pick 1: setup=W_eq1_sp10_leg|equality=1|spacing=10|stop=leg|trail_ma20|L|next_open|buf0.1: TSX HO +1 R/yr (p 0.43); TSX IS +11 R/yr (p 0.00); TSX OOS +10 R/yr (p 0.01); US IS +5 R/yr (p 0.06); US OOS +8 R/yr (p 0.06)
    - IS pick 2: setup=W_eq1_sp10_top|equality=1|spacing=10|stop=top|trail_ma20|L|close|buf0.1: TSX HO +1 R/yr (p 0.43); TSX IS +8 R/yr (p 0.00); TSX OOS +8 R/yr (p 0.00); US IS +2 R/yr (p 0.13); US OOS +7 R/yr (p 0.04)
    - IS pick 3: setup=W_eq1_sp10_top|equality=1|spacing=10|stop=top|trail_ma20|L|next_open|buf0.5: TSX HO +3 R/yr (p 0.27); TSX IS +7 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.02); US IS +2 R/yr (p 0.20); US OOS +7 R/yr (p 0.03)
    - as taught | 2R: TSX HO +3 R/yr (p 0.32); TSX IS +3 R/yr (p 0.09); TSX OOS -3 R/yr (p 0.79); US IS +4 R/yr (p 0.16); US OOS -11 R/yr (p 0.99)
    - as taught | be1_2R: TSX HO +3 R/yr (p 0.25); TSX IS +1 R/yr (p 0.26); TSX OOS -4 R/yr (p 0.84); US IS +3 R/yr (p 0.17); US OOS -8 R/yr (p 0.97)
    - as taught | be1_3R: TSX HO +2 R/yr (p 0.34); TSX IS -0 R/yr (p 0.58); TSX OOS -4 R/yr (p 0.82); US IS +2 R/yr (p 0.29); US OOS -8 R/yr (p 0.96)
    - as taught | half1R_trail2atr: TSX HO +0 R/yr (p 0.46); TSX IS +1 R/yr (p 0.32); TSX OOS -4 R/yr (p 0.99); US IS -3 R/yr (p 0.92); US OOS -2 R/yr (p 0.81)
    - as taught | time10: TSX HO +2 R/yr (p 0.32); TSX IS +1 R/yr (p 0.34); TSX OOS -4 R/yr (p 0.97); US IS -1 R/yr (p 0.68); US OOS -1 R/yr (p 0.68)
    - as taught | time5: TSX HO -0 R/yr (p 0.51); TSX IS +0 R/yr (p 0.37); TSX OOS -1 R/yr (p 0.73); US IS -1 R/yr (p 0.64); US OOS +1 R/yr (p 0.33)
    - as taught | trail2atr: TSX HO +0 R/yr (p 0.45); TSX IS +0 R/yr (p 0.35); TSX OOS -5 R/yr (p 0.99); US IS -4 R/yr (p 0.97); US OOS -4 R/yr (p 0.91)
  - Also run: S14X_US
  - Also run: S14X_HO

### S15 - Triangle breakout (ascending / symmetrical)  [REJECTED]
- Sources: Booming Bulls, Power of Stocks (3 refs). Taught on: Nifty, Indian stocks
- Rule: Big-candle close beyond the flat side (ascending) or either side (symmetrical) of a triangle
- Ladder: 1) strong up-move first, never trade the first pullback (3BZm5xDCxnU) -> 2) higher lows under flat resistance -> 3) more time near resistance = bigger break (hrGUwS58o-I) -> 4) breakout 2/3-3/4 to apex (Murphy) -> 5) invalid if price gaps below the last higher low
- Verdict: Good IS, collapsed OOS: 97 configs pass luck test IS -> 0 OOS (long +0.10R -> 0.00R).
- S15: 864 configs graded. Funnel (main fees): 864 -> 336 -> 153 -> 97 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: stop: candle, last_low; triangle: ascending, both, symmetrical; touches: 2, 3; gate: plain, power; target: 2R, 2x_pullback, base_height; entry: close, next_open; buf: 0.1, 0.5
  - as taught PoS daily (ascending, power, prior move, 2x pullback) (long): IS 27 tr, -0.11R, edge -0.21; OOS 11 tr, -0.10R, edge -0.40
  - as taught BB daily (symmetrical, power, 2R) (long): IS 212 tr, +0.11R, edge +0.12; OOS 135 tr, -0.18R, edge -0.13
  - as traded daily (both, two touches, 2R) (long): IS 1043 tr, +0.15R, edge +0.06; OOS 642 tr, +0.02R, edge -0.06
  - True edge, skill vs random twins (S15):
    - IS pick 1: stop=candle|triangle=both|touches=2|gate=plain|2R|L|close|buf0.1: TSX IS +10 R/yr (p 0.01); TSX OOS -2 R/yr (p 0.63)
    - IS pick 2: stop=candle|triangle=both|touches=2|gate=plain|2R|L|next_open|buf0.1: TSX IS +10 R/yr (p 0.00); TSX OOS -4 R/yr (p 0.81)
    - IS pick 3: stop=candle|triangle=symmetrical|touches=2|gate=plain|2R|L|close|buf0.1: TSX IS +8 R/yr (p 0.01); TSX OOS -3 R/yr (p 0.72)
    - as taught BB daily (symmetrical, power, 2R): TSX IS +2 R/yr (p 0.13); TSX OOS -2 R/yr (p 0.82)
    - as taught PoS daily (ascending, power, prior move, 2x pullback): TSX IS -0 R/yr (p 0.84); TSX OOS -0 R/yr (p 0.89)
    - as traded daily (both, two touches, 2R): TSX IS +4 R/yr (p 0.14); TSX OOS -4 R/yr (p 0.84)

### S16 - Flag / pole-and-flag continuation  [REJECTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (8 refs). Taught on: Indian stocks, Bank Nifty, forex
- Rule: After a strong impulse (pole), a shallow counter-trend pause (flag) breaks in the impulse direction
- Ladder: 1) pole = big momentum candle(s) -> 2) flag retraces < 50% of pole (gALuCTUzzxE), 1-3 weeks [M] / 5-15 sessions [V] -> 3) flag volume lower than pole volume (6UvWqu-c1Ic) -> 4) daily simple version: pole -> 1-2 red candles -> first green candle -> buy its high next day (DjPAruVzm5Q) -> 5) confluence with range/channel breakout = size up -> 6) intraday: only if opening move not stretched (Bank Nift
- Verdict: No edge (best p 0.96). Watch: shallow flag <=38.2%, 3-10 bars, +0.28/+0.19R but ~250/160 trades.
- S16: 972 configs graded. Funnel (main fees): 972 -> 864 -> 307 -> 68 -> 43 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: pole: 1.5, 2.0, 3.0; depth: 38.2, 50.0, 61.8; length: 1-2, 3-10, 5-15; target: 1.5R, 2R, opp; entry: close, next_open; buf: 0.1, 0.5, 1.0
  - as taught (pole>=2 ATR, depth<=50%, 5-15 bars, flag volume fades, 2R, next open) (long): IS 219 tr, -0.09R, edge -0.25; OOS 103 tr, +0.25R, edge +0.19
  - as traded (pole>=2 ATR, depth<=61.8%, 3-10 bars, 2R) (long): IS 1110 tr, +0.10R, edge -0.00; OOS 684 tr, +0.10R, edge +0.03
  - pole-length target (long): IS 1134 tr, +0.07R, edge -0.03; OOS 698 tr, +0.10R, edge +0.01
  - PoS daily simple (1-2 red then first green, buy its high) (long): IS 1668 tr, +0.01R, edge -0.01; OOS 1157 tr, +0.03R, edge -0.01
  - True edge, skill vs random twins (S16):
    - IS pick 1: pole=1.5|depth=38.2|length=3-10|2R|L|next_open|buf0.1: TSX IS +4 R/yr (p 0.05); TSX OOS +2 R/yr (p 0.15)
    - IS pick 2: pole=1.5|depth=38.2|length=3-10|opp|L|next_open|buf1.0: TSX IS +2 R/yr (p 0.05); TSX OOS -0 R/yr (p 0.58)
    - IS pick 3: pole=2|depth=38.2|length=3-10|2R|L|next_open|buf0.1: TSX IS +3 R/yr (p 0.06); TSX OOS +2 R/yr (p 0.16)
    - PoS daily simple (1-2 red then first green, buy its high): TSX IS -1 R/yr (p 0.60); TSX OOS -1 R/yr (p 0.54)
    - as taught (pole>=2 ATR, depth<=50%, 5-15 bars, flag volume fades, 2R, next open): TSX IS -3 R/yr (p 0.99); TSX OOS +2 R/yr (p 0.08)
    - as traded (pole>=2 ATR, depth<=61.8%, 3-10 bars, 2R): TSX IS -0 R/yr (p 0.52); TSX OOS +2 R/yr (p 0.32)
    - pole-length target: TSX IS -2 R/yr (p 0.69); TSX OOS +1 R/yr (p 0.41)

### S17 - Cup & handle / rounding bottom breakout  [REJECTED]
- Sources: Booming Bulls, Power of Stocks (4 refs). Taught on: Indian stocks (Zomato, Mazagon examples), gold
- Rule: Break above the prior high (rim) after a rounded base and a shallow handle
- Ladder: 1) rounded base (often post-IPO or post-crash) -> 2) rally back to prior high -> 3) shallow handle (smaller retracement = stronger; deep handle disqualifies) -> 4) pause/small correction near the high, then break -> 5) deep curve: buy the handle retest; shallow: buy the breakout (-KVuAe6akao) -> 6) leaders that recover to highs first after a crash (qtcBbh1L9lg)
- Verdict: Too rare (24 configs with >=100 IS trades), avgR ~0.
- S17: 1,296 configs graded. Funnel (main fees): 1296 -> 24 -> 12 -> 4 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: cup_min: 30; handle_pct: 33; stop: candle, handle; quality: base; target: 2R, 3R, opp; entry: close, next_open; buf: 0.1, 0.5
  - as taught (60-bar cup, handle <15%, handle stop, cup projection) (long): IS 15 tr, +0.15R, edge +0.06; OOS 17 tr, -0.48R, edge -0.29
  - as traded (30-bar cup, handle <33%, candle stop, 2R) (long): IS 121 tr, +0.02R, edge +0.01; OOS 87 tr, +0.07R, edge +0.13
  - True edge, skill vs random twins (S17):
    - IS pick 1: cup_min=30|handle_pct=33|stop=candle|quality=base|2R|L|close|buf0.1: TSX IS +0 R/yr (p 0.36); TSX OOS +2 R/yr (p 0.24)
    - IS pick 2: cup_min=30|handle_pct=33|stop=candle|quality=base|2R|L|next_open|buf0.5: TSX IS +0 R/yr (p 0.37); TSX OOS -1 R/yr (p 0.69)
    - IS pick 3: cup_min=30|handle_pct=33|stop=candle|quality=base|opp|L|close|buf0.5: TSX IS +0 R/yr (p 0.43); TSX OOS +2 R/yr (p 0.25)
    - as taught (60-bar cup, handle <15%, handle stop, cup projection): TSX IS +0 R/yr (p 0.44); TSX OOS -1 R/yr (p 0.74)
    - as traded (30-bar cup, handle <33%, candle stop, 2R): TSX IS +0 R/yr (p 0.47); TSX OOS +1 R/yr (p 0.24)

### S18 - Trendline 3rd-touch entry and trendline break (discretionary)  [NOT TESTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (4 refs). Taught on: Nifty, Indian stocks, S&P
- Rule: Price touches a valid trendline for the 3rd+ time (bounce) or closes through it (break)
- Ladder: 1) line activated only by the 3rd touch (u6CumeL2gx8) -> 2) ~45-degree slope; steep line -> wait for M/W (2nGrPAEN3vw) -> 3) break valid on ~3% close beyond or 2 closes [M] -> 4) many-touch line: break "blasts", 75% size on break + 25% on first pullback (2nGrPAEN3vw) -> 5) best: flat base under a falling line
- Why not tested: Not tested. | Type: Entry. Partly taught on Indian/forex/gold markets - check transfer. Sources disagree on how to draw (wicks vs bodies; AK rejects diagonal lines as subjective, C06JMxI6Tsg) -> discretionary; use as checklist. The precise Sperandeo version is cod

### S19 - Swing-structure reversal: higher low then break of prior swing high (Sperandeo 1-2-3)  [REJECTED]
- Sources: Adam Khoo, Power of Stocks (6 refs). Taught on: US stocks (AK), Indian stocks/Nifty (PoS)
- Rule: After a downtrend, price makes a higher low and then closes above the most recent swing high (point A)
- Ladder: 1) downtrend line broken (Sperandeo line: highest high to the high before the lowest low, not cutting price) -> 2) don't buy the first break; wait for pullback to a higher low B -> 3) close above A with a bullish candle (if it gaps above A on a bearish candle, wait) -> 4) at support (PoS hiwFUlEkpdU) -> 5) first pullback/first break of a new move only (later waves weaker); mirror: first break of t
- Verdict: No edge: long ~100% profitable, median edge +0.05/+0.07R (drift); best RW p 0.61.
- S19: 384 configs graded. Funnel (main fees): 384 -> 240 -> 116 -> 90 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: pivot: 2, 3, 5; trendline: False, True; location: False, True; volume: False, True; target: 2R, 3R; entry: close, next_open; buf: 0.1, 0.5
  - as taught (AK 1-2-3, confirmed pivots, trendline break) (long): IS 148 tr, +0.19R, edge +0.12; OOS 94 tr, +0.07R, edge -0.04
  - as traded (PoS first structure break) (long): IS 692 tr, +0.14R, edge +0.07; OOS 531 tr, +0.12R, edge -0.01
  - True edge, skill vs random twins (S19):
    - IS pick 1: pivot=2|trendline=False|location=True|volume=False|3R|L|close|buf0.5: TSX IS +5 R/yr (p 0.02); TSX OOS +3 R/yr (p 0.21); US IS +0 R/yr (p 0.47); US OOS +1 R/yr (p 0.41)
    - IS pick 2: pivot=2|trendline=False|location=True|volume=True|2R|L|close|buf0.1: TSX IS +3 R/yr (p 0.02); TSX OOS +2 R/yr (p 0.12); US IS +1 R/yr (p 0.39); US OOS +1 R/yr (p 0.42)
    - IS pick 3: pivot=2|trendline=False|location=True|volume=True|2R|L|close|buf0.5: TSX IS +3 R/yr (p 0.03); TSX OOS +3 R/yr (p 0.10); US IS +0 R/yr (p 0.49); US OOS +1 R/yr (p 0.41)
    - as taught (AK 1-2-3, confirmed pivots, trendline break): TSX IS +1 R/yr (p 0.14); TSX OOS -0 R/yr (p 0.60); US IS -1 R/yr (p 0.86); US OOS -1 R/yr (p 0.68)
    - as traded (PoS first structure break): TSX IS +3 R/yr (p 0.16); TSX OOS -1 R/yr (p 0.56); US IS -1 R/yr (p 0.58); US OOS +12 R/yr (p 0.04)
  - Also run: S19_US

### S20 - Failed breakout / bull-bear trap of a swing level (close back inside), daily  [REJECTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (19 refs). Taught on: Nifty, gold, BTC, forex, US stocks
- Rule: Price breaks a key high (low) and then closes back inside the prior range -> trade the opposite way
- Ladder: 1) key level = prior swing high/low or range edge never closed above before (SxQwiHBfHUs) -> 2) close back inside (trap) on the same or next candle -> 3) fast, large reversal candle (PoS Smugllj7uAw) / shooting star or evening star best (ZEqfiVSbDG0) -> 4) RSI divergence as extra (SxQwiHBfHUs) -> 5) first touch from far away more likely to fail (zHXuZJ_cbx0) -> 6) at ATH look for failure (QHhCv53U
- Verdict: No edge (3,456 configs, best p 0.70). S20_v2 '55-day low trap + bullish engulfing' passed TSX IS/OOS (+0.17/+0.30R, p .03/.02) but FAILED the US cold test (avgR ~0, p .44-.51) -> dropped.
- S20_v2: 3,456 configs graded. Funnel (main fees): 3456 -> 3456 -> 1219 -> 823 -> 76 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - as taught (long): IS 2143 tr, -0.03R, edge +0.01; OOS 1462 tr, -0.03R, edge +0.01
  - as traded (long): IS 7758 tr, -0.06R, edge +0.01; OOS 5514 tr, -0.04R, edge +0.07
  - 55-day + engulfing (near-miss), stop 0.1 (long): IS 346 tr, +0.17R, edge +0.20; OOS 239 tr, +0.30R, edge +0.28
  - 55-day + engulfing, stop 0.5 (long): IS 351 tr, +0.17R, edge +0.11; OOS 236 tr, +0.30R, edge +0.24
  - 55-day + engulfing, stop 1.0 (long): IS 346 tr, +0.17R, edge +0.15; OOS 232 tr, +0.26R, edge +0.20

### S21 - Prior-day high/low levels: sweep-and-fade (BB) vs breakout (PoS)  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (3 refs). Taught on: Gold, USDJPY (BB); Bank Nifty options (PoS)
- Rule: Price trades through the previous day's high (low)
- Ladder: BB fade: 1) PDH/PDL by bodies -> 2) close back inside -> 3) time window 12:00-22:30 IST -> 4) small close-back candle -> wait for 2nd -> 5) for current-day H/L need 70-80% of daily ATR used (IOBoaM71MUA). PoS breakout: 1) PDH/PDL break at 9:15-9:30 -> 2) scalp-tight stop, swing target 1:3 -> 3) trail
- Why not tested: Not tested (needs intraday). | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. The direction disagreement (fade vs follow) is the main dial; testing both on the same levels is a clean experiment. Flag: forex/gold/Indian index. | Sourc

### S22 - Fixed-time range sweep & reclaim (session box trap)  [NOT TESTED]
- Sources: Booming Bulls (2 refs). Taught on: Gold (XAUUSD), EURUSD
- Rule: A fixed-time range (e.g. 11:30-12:30 IST or 10:00 body H/L) is swept and price closes back inside
- Ladder: 1) mark range on bodies -> 2) wait until a fixed time (after Tokyo-London overlap / after 11:45) -> 3) sweep beyond edge + close back inside -> 4) skip day if it triggers too early (uUa61jN45vM) -> 5) one trade/day
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Flag: forex/gold session logic; TSX has no Asia/London sessions -> transfer uncertain (could map to first-hour range). | Sources: 2 videos/docs from Boomin

### S23 - Opening-range failed-breakout fade (ORB trap)  [NOT TESTED]
- Sources: Booming Bulls (1 refs). Taught on: US stocks (Apple)
- Rule: Price breaks the first 15-min range and a candle closes back inside -> trade the opposite way
- Ladder: 1) 3-min chart, first 15 min = range -> 2) range < 1% of price -> 3) entry within ~2 h of open -> 4) one trade per day
- Why not tested: Not tested. | Type: Entry. Mirror of S12 on the same range -> test both together. | Sources: 1 videos/docs from Booming Bulls. Ease of coding 3/3. Raw candidates: c072.

### S24 - Liquidity sweep into a higher-timeframe demand/supply zone ("sniper entry")  [NOT TESTED]
- Sources: Booming Bulls (3 refs). Taught on: Gold, crude, BTC, forex
- Rule: Price runs the stops below an obvious low into an HTF demand zone and prints a strong reversal candle
- Ladder: 1) obvious retail level (double/triple bottom) -> 2) sweep below it -> 3) price reaches HTF demand zone (wick-to-body) -> 4) strong green reversal close -> 5) pyramid on first retest; variant: internal liquidity at the 50-60% retracement (rFrFhpwJJOc)
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Zone drawing is subjective -> checklist. Its codeable core is S20 (trap of a swing level). Flag: forex/gold; source says less reliable in Indian equities d

### S25 - Volume-profile levels: break LVNs, fade HVN/POC/value-area edges  [NOT TESTED]
- Sources: Booming Bulls (6 refs). Taught on: Gold futures (GC), EURUSD
- Rule: Price reaches a prior-session volume-profile level (LVN = breakout level; POC/HVN/VAH/VAL = reversal level)
- Ladder: 1) fixed-range VP on prior session (or prior day to 16:00 IST) -> 2) LVN: trade the break with confirmation candle; HVN/POC/VA edge: wait for sweep + close back -> 3) VAH only sells / VAL only buys (zYGUL82NsS4) -> 4) Asia box around POC then London/NY break (V4fYRC5sZYE) -> 5) order-flow delta absorption at those levels (ieZ--wMeSxE)
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Needs intraday volume-at-price (TradingView has VP tools). Flag: gold/forex. | Sources: 6 videos/docs from Booming Bulls. Ease of coding 2/3. Raw candidate

### S26 - Fair value gap (FVG) retrace and inverse FVG  [NOT TESTED]
- Sources: Booming Bulls (3 refs). Taught on: ETH, USDJPY, gold
- Rule: A 3-candle imbalance (candle 1 high < candle 3 low, big middle body) is revisited and a confirming candle prints
- Ladder: 1) FVG quality: big middle body, small neighbours -> 2) entry in the deeper half (discount for longs) -> 3) confirming candle -> 4) if price closes through the gap, trade the retest from the other side (IFVG) -> 5) with structure bias (BOS) and ATR-consumption context (5glwOHR6nEA)
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. FVG is mechanical and could be tested on daily bars (Claude adaptation, not taught) -> B because taught on 1h and below. | Sources: 3 videos/docs from Boom

### S27 - Smart Money Concepts: order block + BOS/CHoCH bias (discretionary)  [NOT TESTED]
- Sources: Booming Bulls (2 refs). Taught on: Bank Nifty, gold, USDJPY
- Rule: Price returns to a higher-timeframe order block (small candle before an impulse leaving an FVG) in the direction of structure bias
- Ladder: 1) bias from BOS/CHoCH -> 2) HTF OB or FVG -> 3) drop 1-2 TFs for a confirmation candle -> 4) BB identity: pick momentum vs reversal side; only 3 areas of interest (triple top/bottom, OB, session-overlap H/L)
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Source itself says SMC = price action with new names (OB ~ supply/demand, sweep ~ trap). Codeable parts are covered by S20/S26. | Sources: 2 videos/docs fr

### S28 - RSI re-entry from overbought/oversold (and M/W shape on RSI)  [REJECTED]
- Sources: Booming Bulls, Power of Stocks (3 refs). Taught on: Bank Nifty, gold, Indian stocks/indices
- Rule: RSI(14) moves beyond 70 (30) and comes back inside the band
- Ladder: 1) base re-entry -> 2) confirming candle colour (red for sells, green for buys, UOPJbSLBoO8) -> 3) RSI forms an M above 70 / W below 40 (indices) or 30 (stocks); trade the break of the M/W middle swing candle (EHHj-KKTlME) -> 4) daily trend filter for direction (z_D7hYoGILw example) -> 5) never trade divergence alone
- Verdict: No edge: median edge -0.01R; best 70/40 confirm RW p 0.93.
- S28: 864 configs graded. Funnel (main fees): 864 -> 504 -> 136 -> 87 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: bands: 70/30, 70/40, 80/20; shape: confirm, reentry, shape; gate: colour, colour+trend, none, trend; target: 2R, opposite_band, rsi50; entry: close, next_open; buf: 0.1, 0.5
  - as taught BB (70/30, colour, confirming-candle break proxy) (long): IS 811 tr, -0.10R, edge -0.19; OOS 626 tr, +0.09R, edge +0.02
  - as traded (70/30 re-entry, next open) (long): IS 999 tr, -0.04R, edge -0.05; OOS 725 tr, +0.09R, edge +0.12
  - PoS daily adaptation (70/40 RSI M/W, middle-candle break) (long): IS 849 tr, +0.14R, edge +0.04; OOS 615 tr, -0.00R, edge -0.11
  - True edge, skill vs random twins (S28):
    - IS pick 1: bands=70/40|shape=confirm|gate=colour|opposite_band|L|next_open|buf0.1: TSX IS +12 R/yr (p 0.02); TSX OOS +5 R/yr (p 0.28)
    - IS pick 2: bands=70/30|shape=reentry|gate=none|rsi50|L|close|buf0.1: TSX IS +7 R/yr (p 0.03); TSX OOS +13 R/yr (p 0.03)
    - IS pick 3: bands=70/40|shape=confirm|gate=none|opposite_band|L|next_open|buf0.1: TSX IS +11 R/yr (p 0.04); TSX OOS +6 R/yr (p 0.28)
    - PoS daily adaptation (70/40 RSI M/W, middle-candle break): TSX IS +2 R/yr (p 0.26); TSX OOS -8 R/yr (p 0.97)
    - as taught BB (70/30, colour, confirming-candle break proxy): TSX IS -10 R/yr (p 1.00); TSX OOS +2 R/yr (p 0.39)
    - as traded (70/30 re-entry, next open): TSX IS -3 R/yr (p 0.80); TSX OOS +9 R/yr (p 0.07)

### S29 - Filter: RSI 60/40 regime and "range shift" filter  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (6 refs). Taught on: Indian stocks/indices
- Rule: RSI(14) holding above 60 = uptrend momentum; below 40 = downtrend; 40-60 = sideways
- Ladder: 1) regime from RSI band -> 2) range shift: uptrend RSI falls and is rejected at 60 from below -> look for shorts; downtrend RSI holds 40 -> buy zone -> 3) confirmed when the opposite band breaks -> 4) use as filter for other entries (Murphy: trending regime -> 40/60, ranging -> 30/70)
- Why not tested: Related: rsi_pullback_uptrend [PS/M] tested (no edge vs B&H). The regime-filter use is not tested. | Type: Filter. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Test as a filter on S09/S19 entries (e.g., only take longs when weekly RSI > 40/60). | Sources: 6 videos/docs from Booming Bulls, Power of Stocks, TA book

### S30 - Dual-timeframe RSI positional setup (weekly RSI > 40 -> daily RSI > 60)  [REJECTED]
- Sources: Power of Stocks (2 refs). Taught on: Indian stocks (Amara Raja, Bata, Escorts examples)
- Rule: Weekly RSI(14) crosses above 40 from below, then the first daily RSI cross above 60
- Ladder: 1) weekly RSI crosses above 40 (downtrend momentum broken) -> watchlist -> 2) first daily RSI cross above 60 after that -> 3) buy above that daily candle high -> 4) skip if signal candle is oversized -> 5) later daily 60-crosses valid while weekly > 40 (lower probability); intraday version: daily RSI > 60 then 10-min RSI 60 cross (FkVwoRUogAg)
- Verdict: No edge, regime-dependent: long profitable 36% IS / 94% OOS.
- S30: 2,160 configs graded. Funnel (main fees): 2160 -> 2128 -> 373 -> 151 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: weekly: 40, 45, 50; daily: 55, 60, 65; cross: any, first; wait: 10, 20, 40, any; size: 2, 3, none; target: 2R, 3R; entry: close, next_open; buf: 0.1, 0.5
  - as taught (daily close-confirmed adaptation) (long): IS 213 tr, -0.03R, edge -0.19; OOS 191 tr, +0.08R, edge +0.03
  - as traded (weekly 50, daily 55, any cross) (long): IS 2097 tr, +0.07R, edge -0.03; OOS 1326 tr, +0.05R, edge -0.02
  - True edge, skill vs random twins (S30):
    - IS pick 1: weekly=50|daily=60|cross=first|wait=20|size=none|2R|L|close|buf0.5: TSX IS +4 R/yr (p 0.03); TSX OOS +6 R/yr (p 0.03)
    - IS pick 2: weekly=50|daily=60|cross=first|wait=20|size=3|2R|L|close|buf0.5: TSX IS +4 R/yr (p 0.03); TSX OOS +6 R/yr (p 0.02)
    - IS pick 3: weekly=50|daily=60|cross=first|wait=20|size=none|3R|L|close|buf0.5: TSX IS +4 R/yr (p 0.04); TSX OOS +7 R/yr (p 0.02)
    - as taught (daily close-confirmed adaptation): TSX IS -3 R/yr (p 0.94); TSX OOS +1 R/yr (p 0.40)
    - as traded (weekly 50, daily 55, any cross): TSX IS -4 R/yr (p 0.74); TSX OOS -4 R/yr (p 0.65)

### S31 - RSI divergence with a price trigger (only near-term divergences)  [KEPT (weak)]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (7 refs). Taught on: Bank Nifty, Indian stocks, US stocks
- Rule: Price makes a higher high (lower low) while RSI makes a lower high (higher low)
- Ladder: 1) base divergence -> 2) the two pivots only 3-5 bars (PoS EVAcrcSa1Ec) / 3-25 bars (CvgnoBNRXt4) / 3-10 candles (EHHj-KKTlME) apart -> 3) trigger: break of the alert candle / range low / trendline / EMA (never enter on divergence alone) -> 4) confluence: double top, 200 EMA, rejection candle (qtvzG4TI3HU) -> 5) AK: divergence on 2 of 3 indicators (MACD/RSI/stoch) + confirming candle
- Code: ta2/strategies (see EVIDENCE there). Variations below were tested and NOT chosen.
- S31: 768 configs graded. Funnel (main fees): 768 -> 760 -> 397 -> 277 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: spacing: 3-10, 3-25, 3-5; indicator: rsi, two3; trigger: alert, range; confluence: double, ema200, none, rejection; target: 1.5R, 2R; entry: close, next_open; buf: 0.1, 0.5
  - as taught (RSI, 3-10 bars, alert break, next open) (long): IS 2478 tr, +0.12R, edge +0.07; OOS 1897 tr, +0.11R, edge +0.07
  - as traded (RSI, 3-25 bars, alert break close) (long): IS 3912 tr, +0.12R, edge +0.05; OOS 2882 tr, +0.14R, edge +0.11
  - AK (2 of 3, 3-25 bars, confirming candle) (long): IS 3307 tr, +0.09R, edge +0.05; OOS 2553 tr, +0.13R, edge +0.11
  - True edge, skill vs random twins (S31):
    - AK (2 of 3, 3-25 bars, confirming candle): TSX IS +10 R/yr (p 0.10); TSX OOS +32 R/yr (p 0.01); US IS +24 R/yr (p 0.08); US OOS +26 R/yr (p 0.12)
    - IS pick 1: spacing=3-25|indicator=rsi|trigger=alert|confluence=ema200|2R|L|next_open|buf0.1: TSX IS +11 R/yr (p 0.00); TSX OOS +4 R/yr (p 0.19); US IS +7 R/yr (p 0.12); US OOS +6 R/yr (p 0.23)
    - IS pick 2: spacing=3-25|indicator=two3|trigger=alert|confluence=ema200|2R|L|next_open|buf0.1: TSX IS +8 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.13); US IS +6 R/yr (p 0.12); US OOS +3 R/yr (p 0.36)
    - IS pick 3: spacing=3-25|indicator=two3|trigger=alert|confluence=double|2R|L|close|buf0.1: TSX IS +16 R/yr (p 0.01); TSX OOS +24 R/yr (p 0.02); US IS +11 R/yr (p 0.23); US OOS +49 R/yr (p 0.01)
    - as taught (RSI, 3-10 bars, alert break, next open): TSX IS +11 R/yr (p 0.05); TSX OOS +15 R/yr (p 0.08); US IS -8 R/yr (p 0.68); US OOS +7 R/yr (p 0.37)
    - as traded (RSI, 3-25 bars, alert break close): TSX IS +13 R/yr (p 0.08); TSX OOS +36 R/yr (p 0.01); US IS +8 R/yr (p 0.32); US OOS +36 R/yr (p 0.09)

### S32 - 5-EMA alert-candle reversal (Power of Stocks signature setup)  [NOT TESTED]
- Sources: Power of Stocks (5 refs). Taught on: Bank Nifty, Indian F&O stocks, BTC, gold, US stocks
- Rule: An "alert" candle sits entirely clear of the 5-period EMA; enter when a later candle breaks the alert candle's low (sell) or high (buy)
- Ladder: 1) alert candle (body and wicks not touching 5 EMA); a new clear candle replaces it -> 2) sell on 5m, buy on 15m -> 3) regime: only use when price has crossed the day's opening price 2-3+ times (two-sided day); don't fade one-way days (ZwXNbEWWnfo) -> 4) size up at unfilled daily gaps or after a range shift (fBTMspiqjS4) -> 5) gap-up F&O stocks: pre-open scan, max 5 shorts/day (xccdGzbI1Yw) -> 6) 
- Why not tested: Not tested (needs intraday). | Type: Entry. Partly taught on Indian/forex/gold markets - check transfer. Fully mechanical; the opening-price cross count is a neat sideways/trend classifier worth testing on its own. | Sources: 5 videos/docs from Power of Stocks. Ease of coding 3/3.

### S33 - Filter: Over-extension / stretch flag (distance from mean, streaks, 90-degree runs)  [NOT TESTED]
- Sources: Power of Stocks (8 refs). Taught on: Gold, BTC, Indian indices, Adani stocks
- Rule: Price is far from its mean (5 EMA on yearly/monthly, 20 EMA, monthly 10 SMA) or has run 3-5 candles in a row
- Ladder: 1) stretch measure -> 2) streak of 3+ (Murphy/PoS) or 4-5 strong candles -> 3) near-vertical (~90 degree) run with no red candle (KjTbe5QvYP0, ESwCtFhFjQI) -> 4) first wicked/negative monthly candle after the run -> 5) action: don't buy / book profit / trim; short only the second pullback (KgklWvJqkuw)
- Why not tested: Not tested. | Type: Filter. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Use as a risk overlay: does skipping entries when stretched improve S09/S16? AK opposite view: buy sharp 90-degree DROPS (S35). | Sources: 8 videos/docs f

### S34 - Monthly lower Bollinger Band touch = index accumulation zone  [REJECTED]
- Sources: Power of Stocks (1 refs). Taught on: Nifty / Bank Nifty
- Rule: Monthly candle touches the lower Bollinger Band (20,2) on the index
- Ladder: 1) monthly lower-band touch -> 2) uptrend usually resumes 2-4 months later -> 3) upper-band touches mean nothing -> 4) VIX regime: sustained VIX rise = correction coming
- Verdict: True but rare: monthly lower-BB touches on XIU won 100% (6 events IS, 2-3 OOS). ~10 trades/yr stock-level, skill +17 R/yr OOS p .05-.06: not proven.

### S35 - Capitulation / sharp-drop rebound buy (90-degree drop, 8-10 red candles)  [REJECTED]
- Sources: Adam Khoo, Booming Bulls (4 refs). Taught on: S&P, US stocks (AK); Indian stocks (BB)
- Rule: A near-vertical drop (8-10 consecutive red candles, or a 5-10% fall in 1-2 days on a quality name)
- Ladder: 1) base sharp drop -> 2) full stochastic < 20 and price outside the lower BB (owipUd-xyy0) -> 3) quality stock/index only (UAmqu_au61M) -> 4) false double bottom / stop-run below prior low then close back above -> 5) media capitulation ("worst day" headline) or VIX spike as proxy (LSwsppvXnb4)
- Verdict: No edge: ~50% profitable, median R 0.00/0.01.
- S35: 576 configs graded. Funnel (main fees): 576 -> 512 -> 259 -> 201 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: drop: drop10_1, drop10_2, drop10_5, drop5_1, drop5_2, drop5_5, drop8_1, drop8_2, drop8_5, red5, red7; oscillator: bb_stoch, none, rsi2; target: 2R, time10, time3, time5; entry: close, next_open; buf: 0.1, 0.5
  - as taught (5% in 2 days, stochastic + BB, rebound, 5 days) (long): IS 712 tr, -0.02R, edge +0.02; OOS 367 tr, -0.17R, edge -0.15
  - as traded (5% in 2 days, rebound, 5 days) (long): IS 3537 tr, -0.04R, edge -0.01; OOS 1713 tr, +0.00R, edge +0.01
  - streak adaptation (5 red closes, rebound, 2R) (long): IS 2019 tr, +0.05R, edge +0.09; OOS 1536 tr, -0.01R, edge +0.10
  - True edge, skill vs random twins (S35):
    - IS pick 1: drop=red5|oscillator=rsi2|time3|L|close|buf0.1: TSX IS +11 R/yr (p 0.01); TSX OOS +9 R/yr (p 0.14)
    - IS pick 2: drop=drop8_5|oscillator=none|time3|L|close|buf0.1: TSX IS +13 R/yr (p 0.00); TSX OOS +9 R/yr (p 0.17)
    - IS pick 3: drop=red5|oscillator=none|time3|L|close|buf0.1: TSX IS +11 R/yr (p 0.01); TSX OOS +8 R/yr (p 0.16)
    - as taught (5% in 2 days, stochastic + BB, rebound, 5 days): TSX IS +1 R/yr (p 0.36); TSX OOS -6 R/yr (p 0.89)
    - as traded (5% in 2 days, rebound, 5 days): TSX IS -3 R/yr (p 0.61); TSX OOS +3 R/yr (p 0.41)
    - streak adaptation (5 red closes, rebound, 2R): TSX IS +11 R/yr (p 0.03); TSX OOS +17 R/yr (p 0.06)

### S36 - Bottom-confirmation re-entry after a decline (positive weekly/monthly candle, HL + swing-high break)  [REJECTED]
- Sources: Power of Stocks (7 refs). Taught on: Nifty, BTC, Indian stocks
- Rule: After a decline, wait for a positive weekly (aggressive) or monthly (conservative) candle before buying
- Ladder: 1) base positive weekly/monthly close -> 2) green weekly candle and its high is crossed (sy2VFcUSMEA) -> 3) weekly higher low + break of prior swing high (R6g3pKmJddY) -> 4) index: >= 2-3 big gap-ups (>=1-2%) in a week near lows, then first pullback that holds and breaks up (IIJVxEX-0QM) -> 5) don't buy until 50% of the big down candle is reclaimed (QHhCv53Upnk)
- Verdict: No edge (luck test). Watch: weekly, decline>=20%, higher low, positive week, 2R: +0.28/+0.29R, RW p 0.36; fails US (edge -0.08/-0.03).
- S36: 720 configs graded. Funnel (main fees): 720 -> 388 -> 278 -> 88 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: timeframe: monthly, weekly; confirmation: break, positive; decline: 10, 15, 20; gate: gap2, hl, none, reclaim50; target: 2R, 3R, swing; entry: close, next_open; buf: 0.1, 0.5
  - as taught (weekly green-high close confirmation) (long): IS 365 tr, -0.04R, edge -0.03; OOS 242 tr, +0.08R, edge +0.08
  - as traded (weekly positive candle) (long): IS 993 tr, +0.00R, edge +0.03; OOS 604 tr, +0.17R, edge +0.13
  - monthly conservative (long): IS 474 tr, -0.07R, edge -0.06; OOS 337 tr, +0.06R, edge +0.04
  - True edge, skill vs random twins (S36):
    - IS pick 1: timeframe=weekly|confirmation=positive|decline=20|gate=hl|2R|L|close|buf0.1: TSX IS +5 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.07); US IS +6 R/yr (p 0.09); US OOS +4 R/yr (p 0.29)
    - IS pick 2: timeframe=weekly|confirmation=positive|decline=20|gate=hl|2R|L|next_open|buf0.1: TSX IS +5 R/yr (p 0.01); TSX OOS +5 R/yr (p 0.05); US IS +2 R/yr (p 0.37); US OOS +1 R/yr (p 0.46)
    - IS pick 3: timeframe=weekly|confirmation=positive|decline=20|gate=hl|3R|L|close|buf0.1: TSX IS +5 R/yr (p 0.02); TSX OOS +4 R/yr (p 0.15); US IS +4 R/yr (p 0.28); US OOS +2 R/yr (p 0.39)
    - as taught (weekly green-high close confirmation): TSX IS -1 R/yr (p 0.70); TSX OOS +2 R/yr (p 0.20); US IS +0 R/yr (p 0.44); US OOS +3 R/yr (p 0.29)
    - as traded (weekly positive candle): TSX IS +2 R/yr (p 0.34); TSX OOS +9 R/yr (p 0.16); US IS +9 R/yr (p 0.23); US OOS +21 R/yr (p 0.13)
    - monthly conservative: TSX IS -2 R/yr (p 0.90); TSX OOS +2 R/yr (p 0.25); US IS +6 R/yr (p 0.20); US OOS +1 R/yr (p 0.42)
  - Also run: S36_US

### S37 - Candlestick reversal triggers at location (engulfing, pin/hammer, morning star, one white soldier)  [REJECTED]
- Sources: Adam Khoo, Booming Bulls (7 refs). Taught on: US stocks, Indian stocks, generic
- Rule: A bullish reversal candle forms at support in an uptrend (mirror at resistance)
- Ladder: 1) pattern definition (pin: tail >= 2/3 of range; morning star closes >50% into candle 1; one white soldier opens above prior close, closes above prior open) -> 2) location: at support in uptrend (50>150, at MA/trendline) -> 3) Morris filter: stochastic %D < 20 [M] -> 4) skip candles with range < 1% or > 10% [V] -> 5) HTF level + LTF trigger (CF-3gUqJ0Vs) -> 6) red-bodied hammer or doji: wait for 
- Verdict: No edge: long median edge +0.03/+0.05R (drift).
- S37: 1,152 configs graded. Funnel (main fees): 1152 -> 1152 -> 564 -> 419 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: pattern: all, engulf, morning, pin2, pinrange, soldier, traded, tweezer; morris: 0, 20, 30; range_filter: False, True; expiry: 1, 2, 3; target: 2R, opp; entry: next_open; buf: 0.1, 0.5
  - as taught (daily, next-bar stop) (long): IS 1904 tr, +0.06R, edge +0.03; OOS 1335 tr, -0.01R, edge -0.05
  - as traded (engulfing + hammer, two-bar stop) (long): IS 1134 tr, +0.07R, edge +0.03; OOS 761 tr, -0.05R, edge -0.02
  - True edge, skill vs random twins (S37):
    - IS pick 1: pattern=tweezer|morris=20|range_filter=False|expiry=1|opp|L|next_open|buf0.1: TSX IS +7 R/yr (p 0.01); TSX OOS +0 R/yr (p 0.50)
    - IS pick 2: pattern=tweezer|morris=0|range_filter=False|expiry=2|opp|L|next_open|buf0.1: TSX IS +11 R/yr (p 0.02); TSX OOS +3 R/yr (p 0.34)
    - IS pick 3: pattern=engulf|morris=0|range_filter=False|expiry=3|2R|L|next_open|buf0.1: TSX IS +9 R/yr (p 0.01); TSX OOS +7 R/yr (p 0.11)
    - as taught (daily, next-bar stop): TSX IS +3 R/yr (p 0.28); TSX OOS -7 R/yr (p 0.78)
    - as traded (engulfing + hammer, two-bar stop): TSX IS +2 R/yr (p 0.33); TSX OOS -1 R/yr (p 0.60)

### S38 - "Golden setup": candle-character bias + stop entry at the next round level, many retries  [REJECTED]
- Sources: Booming Bulls, Power of Stocks (8 refs). Taught on: BTC, gold, Nasdaq (PoS)
- Rule: Read the last candle on your timeframe: strong bullish close (near the high) -> only buy above the nearest round level beyond the close; strong bearish -> only sell below; mid-range close -> no trade
- Ladder: 1) candle character (close location in range) -> 2) entry at nearest round level beyond the close in the trade direction -> 3) small stop, >=1:4-1:5 target -> 4) up to 4-5 retries at the same level; shift the level after 2-3 stops -> 5) intraday version: day open +/- nearest round levels with buffer, 4 attempts/day -> 6) weekly version: Monday open, larger round levels, 5-7 attempts -> 7) two cons
- Verdict: No edge, worst: long median -0.54R (stops 0.25-0.5 ATR -> fees eat R).
- S38: 810 configs graded. Funnel (main fees): 810 -> 804 -> 55 -> 31 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: round_step: cad1, cad5, pct05, pct1, pct2; close_zone: 20, 30, 40; gate: body, none, trend200; entry_rule: next_session_stop; retries: 0; target: 3R, 4R, 5R; entry: next_open; buf: 0.25, 0.5, 1.0
  - as taught (daily adaptation: top/bottom 20%, C$1, 0.25 ATR, 4R; no retries) (long): IS 710 tr, -1.00R, edge +0.05; OOS 731 tr, -0.88R, edge +0.06
  - as traded (daily: top/bottom 30%, C$1, 0.5 ATR, 3R; no retries) (long): IS 1562 tr, -0.68R, edge -0.11; OOS 1704 tr, -0.56R, edge -0.09
  - True edge, skill vs random twins (S38):
    - IS pick 1: round_step=cad1|close_zone=20|gate=body|entry_rule=next_session_stop|retries=0|4R|L|next_open|buf1.0: TSX IS +10 R/yr (p 0.01); TSX OOS -17 R/yr (p 0.96)
    - IS pick 2: round_step=cad1|close_zone=20|gate=body|entry_rule=next_session_stop|retries=0|5R|L|next_open|buf1.0: TSX IS +11 R/yr (p 0.02); TSX OOS -18 R/yr (p 0.96)
    - IS pick 3: round_step=cad1|close_zone=20|gate=none|entry_rule=next_session_stop|retries=0|4R|L|next_open|buf1.0: TSX IS +10 R/yr (p 0.02); TSX OOS -19 R/yr (p 0.97)
    - as taught (daily adaptation: top/bottom 20%, C$1, 0.25 ATR, 4R; no retries): TSX IS +2 R/yr (p 0.22); TSX OOS +5 R/yr (p 0.20)
    - as traded (daily: top/bottom 30%, C$1, 0.5 ATR, 3R; no retries): TSX IS -10 R/yr (p 0.98); TSX OOS -17 R/yr (p 0.96)

### S39 - Breakaway gap continuation (gap through a key level on high volume that stays unfilled)  [REJECTED]
- Sources: Booming Bulls, Power of Stocks (8 refs). Taught on: Nifty, Indian stocks; Murphy (US)
- Rule: Price gaps through a pattern/key level (e.g. N-day high, neckline) and the gap is not filled
- Ladder: 1) gap breaks a chart pattern or key S/R -> 2) heavy volume -> 3) unfilled within 1-4 days = confirmed; close back inside gap = failed (7bK0aRbS8nc) -> 4) swing entry after the retest of the gap holds -> 5) trend-aligned "gap & go": holds the day's low / 3-4 days (vS1VRU3hkxk) -> 6) gap after a range breakout continues; very big gap invites profit booking (MSVHZ56iH3c)
- Verdict: No edge: median edge -0.02/-0.09R.
- S39: 3,024 configs graded. Funnel (main fees): 3024 -> 916 -> 486 -> 233 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: gap: atr05, atr1, pct05, pct1, pct2; level: 20, 252, 55; timing: hold1, hold2, hold4, retest; volume: vol1, vol15; target: 1.5R, 2R, 3R; entry: close, next_open; buf: 0.1, 0.5
  - as taught (long): IS 171 tr, +0.17R, edge +0.14; OOS 112 tr, +0.24R, edge +0.29
  - as traded (long): IS 251 tr, +0.03R, edge -0.07; OOS 189 tr, -0.06R, edge -0.19
  - gap retest (long): IS 107 tr, +0.03R, edge -0.09; OOS 60 tr, -0.32R, edge -0.29
  - True edge, skill vs random twins (S39):
    - IS pick 1: gap=pct2|level=20|timing=hold2|volume=vol15|2R|L|next_open|buf0.1: TSX IS +2 R/yr (p 0.06); TSX OOS -1 R/yr (p 0.71)
    - IS pick 2: gap=pct05|level=20|timing=hold4|volume=vol1|2R|L|next_open|buf0.5: TSX IS +2 R/yr (p 0.07); TSX OOS -0 R/yr (p 0.56)
    - IS pick 3: gap=pct2|level=20|timing=hold2|volume=vol1|2R|L|next_open|buf0.1: TSX IS +2 R/yr (p 0.07); TSX OOS -1 R/yr (p 0.78)
    - as taught: TSX IS +1 R/yr (p 0.11); TSX OOS +4 R/yr (p 0.01)
    - as traded: TSX IS -1 R/yr (p 0.75); TSX OOS -4 R/yr (p 0.94)
    - gap retest: TSX IS -1 R/yr (p 0.66); TSX OOS -2 R/yr (p 0.90)

### S40 - Gap vs prior-day candle: next-day direction table (PoS)  [REJECTED]
- Sources: Power of Stocks (4 refs). Taught on: Nifty / Indian stocks
- Rule: Combine the prior day's candle type with today's gap to predict the session direction
- Ladder: Prior doji -> trade in the gap direction; prior bearish + flat open -> continuation down; prior bearish + gap-down -> reversal up (shorts book profits); prior bearish + gap-up > 50% of prior body -> strong up (shorts trapped); prior bullish mirror (flat -> continuation, big gap-up -> profit taking, gap-down below 50% of prior body -> sell); huge gap-up after a positive close often fills (0RDF9zoJ0
- Verdict: Claim '60-70%' false: 0 of 78 configs reach 60% (best ~54%); IS-significant rows vanished OOS; every rule loses after costs.

### S41 - Gap-up fade / fade the over-extended open (intraday)  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (6 refs). Taught on: Nifty, BTC (US open), Indian stocks
- Rule: After a strong run, a large gap-up (or extended pre-open move) fades: short the first weakness after the open
- Ladder: 1) market positive for several days -> 2) gap-up >= 200 Nifty pts (~1%) -> 3) first red 5m candle after the open run-up -> short its low break (i4_tvg32fs4) -> 4) exhaustion gap: fills same day on very high volume (vS1VRU3hkxk) -> 5) half size on big gap days until structure forms (vmcmgsyp9rI)
- Why not tested: Not tested. | Type: Entry. Partly taught on Indian/forex/gold markets - check transfer. A daily-bar proxy (short at open on >X% gap-up after N up days, exit at close) is a Claude adaptation that can be checked first in Python. | Sources: 6 videos/docs from Booming

### S42 - Pre-earnings breakout swing (exit at results) and post-results stall fade  [REJECTED]
- Sources: Booming Bulls, Power of Stocks (3 refs). Taught on: Indian stocks
- Rule: 10-15 trading days before results, a stock breaks out of a key level / consolidation
- Ladder: 1) results >= 4-5 days away (10-15 better) -> 2) breakout/flag/retest/trap/MA support -> 3) stock was consolidating into the event, not running into it (rtaqsi2AexE) -> 4) no new swing trades into major macro events (budget) -> 5) after a run-up into results, a doji/red stall -> short the doji low break
- Verdict: No edge: 3 pass RW IS -> 0 OOS; best avgR -0.04 IS / -0.14 OOS.
- S42: 336 configs graded. Funnel (main fees): 336 -> 312 -> 9 -> 3 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: lead_bars: 10, 15, 5; stop: candle, level; gates: base, consolidation, consolidation+trend50, consolidation+volume, trend200, trend50, volume; target: 3R, before; entry: close, next_open; buf: 0.1, 0.5
  - as taught (10 bars, consolidation breakout, candle stop, exit before results) (long): IS 714 tr, -0.13R, edge -0.07; OOS 586 tr, -0.15R, edge -0.10
  - as traded (15 bars, breakout, level stop, next open, 3R capped before results) (long): IS 768 tr, -0.32R, edge -0.11; OOS 689 tr, -0.24R, edge -0.03
  - True edge, skill vs random twins (S42):
    - IS pick 1: lead_bars=15|stop=level|gates=consolidation|3R|L|next_open|buf0.5: TSX IS +2 R/yr (p 0.33); TSX OOS -7 R/yr (p 0.85)
    - IS pick 2: lead_bars=15|stop=candle|gates=consolidation+trend50|3R|L|next_open|buf0.1: TSX IS +2 R/yr (p 0.34); TSX OOS -8 R/yr (p 0.89)
    - IS pick 3: lead_bars=15|stop=level|gates=consolidation+trend50|3R|L|next_open|buf0.5: TSX IS +2 R/yr (p 0.34); TSX OOS -6 R/yr (p 0.83)
    - as taught (10 bars, consolidation breakout, candle stop, exit before results): TSX IS -3 R/yr (p 0.83); TSX OOS -6 R/yr (p 0.86)
    - as traded (15 bars, breakout, level stop, next open, 3R capped before results): TSX IS -5 R/yr (p 0.93); TSX OOS -2 R/yr (p 0.63)

### S43 - Relative-strength leader selection (stock vs index / sector RS rank)  [KEPT (weak)]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (4 refs). Taught on: US stocks, Indian stocks, TSX (Murphy)
- Rule: Buy the strongest stocks by relative strength vs the index (or in the strongest sectors)
- Ladder: 1) TSX trend -> sector RS rising -> strongest stocks (Murphy top-down) -> 2) RS rating >= 85 (AK) -> 3) stocks at/near ATH while the index is 3-5% below its ATH (MSVHZ56iH3c) -> 4) RRG: prefer sectors moving lagging -> improving (68_65YqI_BQ) -> 5) after a crash, leaders that recover to highs first (qtcBbh1L9lg)
- Code: ta2/strategies (see EVIDENCE there). Variations below were tested and NOT chosen.

### S44 - Sector-index break -> trade the leading heavyweight stock (intraday)  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (3 refs). Taught on: Bank Nifty heavyweights (HDFC, ICICI, Axis, SBI, Kotak)
- Rule: When the sector index breaks its day high/low on a 5-min close, trade the heavyweight that broke its own day high/low at the same time with the strongest candle
- Ladder: 1) at 10:00-10:15 mark sector index day H/L -> 2) index 5m close breaks -> 3) scan 5-6 heavyweights, pick rank 1-2 by candle strength -> 4) trade the stock in the index direction -> 5) PoS: pre-selected buy/sell lists, only trade in list direction; index as management filter (WdrTStxyC7c)
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Maps well to TSX banks (RY, TD, BNS, BMO, CM, NA) vs the financials index; needs 5m data. | Sources: 3 videos/docs from Booming Bulls, Power of Stocks. Eas

### S45 - Sector ETF momentum rotation (own the strongest sectors)  [KEPT (protection)]
- Sources: Adam Khoo, Booming Bulls (3 refs). Taught on: US sector SPDRs (AK), Indian sectors (BB), TSX sectors (Murphy top-down)
- Rule: Rotate into the sector ETFs with the strongest relative strength
- Ladder: 1) rank sector ETFs by RS vs index -> 2) prefer RRG lagging->improving (68_65YqI_BQ) -> 3) index regime filter (S01/S03)
- Code: ta2/strategies (see EVIDENCE there). Variations below were tested and NOT chosen.

### S46 - Top-losers sector ETF rotation (buy the day's weakest sector ETF, sell at +1-3%)  [REJECTED]
- Sources: Power of Stocks (1 refs). Taught on: Indian sector ETFs (healthcare, small-cap)
- Rule: Buy small lots of the day's top-losing liquid sector ETFs
- Ladder: 1) daily top-losing sector ETFs -> 2) liquidity filter -> 3) sell when 1-3% above cost -> repeat
- Verdict: No edge: as traded -0.7%/yr IS, -0.9%/yr OOS vs XIU 5.1/10.8; random baskets did better.

### S47 - ADX + Supertrend + Fibonacci pivot-break intraday system  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (3 refs). Taught on: Bank Nifty / Nifty
- Rule: 5-min candle breaks a daily Fibonacci pivot line in the Supertrend(10,3) direction while 15-min ADX(14) > 20
- Ladder: 1) ADX(14) on 15m > 20 ("trading zone"); fresh rising best -> 2) Supertrend(10,3) direction -> 3) pivot-break trigger (or strong PA candle at a pivot) -> 4) skip if stop > ~150-200 Bank Nifty pts -> 5) max 2 trades/day; stop after a big win; no new trades after ~14:30
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Fully rule-based; flag: Indian index -> test on XIU 5m or TSX large caps. | Sources: 3 videos/docs from Booming Bulls, Power of Stocks. Ease of coding 3/3.

### S48 - Half Trend flip filtered by 15-min DMI direction and ADX > 23  [NOT TESTED]
- Sources: Booming Bulls (1 refs). Taught on: Nifty, Bank Nifty, liquid Indian stocks
- Rule: Half Trend indicator turns green (buy) / red (sell) on a closed 5-min candle
- Ladder: 1) Half Trend flip -> 2) +DI > -DI for longs (DMI length 13 on 15m) -> 3) ADX > 23 -> 4) 2 stops in a day -> stop
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Half Trend is a TradingView community indicator (ATR-based) -> needs reimplementation in Python. | Sources: 1 videos/docs from Booming Bulls. Ease of codin

### S49 - VWAP-filtered pivot / VWAP / day-extreme break after 10:45  [NOT TESTED]
- Sources: Booming Bulls (2 refs). Taught on: Bajaj Finance (same stock every day)
- Rule: After 10:45, price breaks a daily Fibonacci pivot, VWAP or the day's high/low in the VWAP direction
- Ladder: 1) no trades before 10:45 -> 2) VWAP side sets direction -> 3) break trigger -> 4) Stoch RSI cross as optional confirmation -> 5) one target = done; max 2 stops/day
- Why not tested: Not tested. | Type: Entry. Easy to compute from 5m bars on liquid TSX names. 2-3% risk is high vs the 1% default. | Sources: 2 videos/docs from Booming Bulls. Ease of coding 3/3. Raw candidates: c032, c089.

### S50 - 400 EMA trap with time window and 2-candle confirmation (15m)  [NOT TESTED]
- Sources: Booming Bulls (1 refs). Taught on: Crude, US30, gold, BTC
- Rule: Price dips through the 15-min 400 EMA and closes back on the bias side
- Ladder: 1) bias = side of 400 EMA at first candle after 12:00 IST -> 2) entries 12:00-22:00 IST only, 1 trade/day -> 3) trap close back -> 4) two confirming candles (>=1 strong body) or one candle bigger than prior 10
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Flag: forex/commodity time windows. Source asks to backtest >= 1 year first. | Sources: 1 videos/docs from Booming Bulls. Ease of coding 3/3. Raw candidate

### S51 - Intraday 200/50 EMA systems (pullback to 200 EMA, pattern at 200 EMA, gap into 200 MA)  [NOT TESTED]
- Sources: Booming Bulls (4 refs). Taught on: Forex, gold, crude, Nifty
- Rule: On 15-30m charts, price interacts with the 200 EMA (pullback, pattern, or gap into it) and triggers in the trend direction
- Ladder: Variants: (a) after a 200 EMA break, wait for return to the EMA + confirming candle, or new high after consolidation beyond it; never trade the direct break (Hj56fabq2c8) + currency-strength filter; (b) a chart pattern (double bottom, H&S, trap, box, ascending triangle) must form AT the 30m 200 EMA, target 1:3 (vldS7qhIYE8); (c) gap-up into 15m 200 MA, engulfing, buy day-high break (6UvWqu-c1Ic, z
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Daily analogue = S04 (MA pullback) and S14 at the 200 DMA. Flag: forex/gold. | Sources: 4 videos/docs from Booming Bulls. Ease of coding 2/3. Raw candidate

### S52 - 200 EMA break + MACD cross near zero (30m)  [NOT TESTED]
- Sources: Booming Bulls (1 refs). Taught on: Forex / commodities (not gold)
- Rule: Price breaks the 200 EMA and MACD crosses its signal line near the zero line in the same direction
- Ladder: 1) above 200 EMA longs only -> 2) MACD cross near zero -> 3) exit on close back across 200 EMA
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Flag: forex. | Sources: 1 videos/docs from Booming Bulls. Ease of coding 3/3. Raw candidates: c104.

### S53 - MACD: weekly direction + daily signal-line crossovers in that direction [M]  [KEPT (strong)]
- Sources: Booming Bulls (2 refs). Taught on: Stocks/futures (Murphy, Varsity)
- Rule: Daily MACD(12,26,9) crosses above its signal line while weekly MACD is rising
- Ladder: 1) weekly MACD direction -> 2) daily cross in that direction -> 3) best buys well below zero -> 4) histogram turn = exit warning
- Code: ta2/strategies (see EVIDENCE there). Variations below were tested and NOT chosen.
- S53: 128 configs graded. Funnel (main fees): 128 -> 128 -> 22 -> 22 -> 12 -> 12  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: macd: macd12_26_9, macd8_17_9; weekly_direction: False, True; zero_line: False, True; target: hist_turn, opposite_cross; entry: close, next_open; buf: 0.1, 0.5
  - as taught (12/26/9, weekly direction, below/above zero) (long): IS 379 tr, -0.02R, edge +0.02; OOS 246 tr, +0.23R, edge +0.26
  - as traded (12/26/9, weekly direction) (long): IS 2156 tr, -0.01R, edge +0.01; OOS 1423 tr, +0.04R, edge +0.05
  - histogram warning exit (12/26/9, weekly direction) (long): IS 2156 tr, -0.02R, edge +0.02; OOS 1423 tr, -0.00R, edge +0.02
  - True edge, skill vs random twins (S53):
    - IS pick 1: macd=macd12_26_9|weekly_direction=False|zero_line=False|opposite_cross|L|next_open|buf0.5: TSX HO +25 R/yr (p 0.15); TSX IS +34 R/yr (p 0.00); TSX OOS +44 R/yr (p 0.00); US IS +32 R/yr (p 0.02); US OOS +76 R/yr (p 0.00)
    - IS pick 2: macd=macd12_26_9|weekly_direction=False|zero_line=False|opposite_cross|L|next_open|buf0.1: TSX HO +29 R/yr (p 0.15); TSX IS +37 R/yr (p 0.00); TSX OOS +58 R/yr (p 0.00); US IS +36 R/yr (p 0.03); US OOS +85 R/yr (p 0.00)
    - IS pick 3: macd=macd12_26_9|weekly_direction=False|zero_line=True|opposite_cross|L|next_open|buf0.5: TSX HO +35 R/yr (p 0.05); TSX IS +27 R/yr (p 0.00); TSX OOS +38 R/yr (p 0.00); US IS +37 R/yr (p 0.00); US OOS +75 R/yr (p 0.00)
    - as taught (12/26/9, weekly direction, below/above zero): TSX HO +4 R/yr (p 0.14); TSX IS +1 R/yr (p 0.37); TSX OOS +7 R/yr (p 0.01); US IS +9 R/yr (p 0.00); US OOS +7 R/yr (p 0.01)
    - as traded (12/26/9, weekly direction): TSX HO +4 R/yr (p 0.35); TSX IS +1 R/yr (p 0.35); TSX OOS +8 R/yr (p 0.05); US IS +6 R/yr (p 0.15); US OOS +4 R/yr (p 0.28)
    - histogram warning exit (12/26/9, weekly direction): TSX HO -0 R/yr (p 0.51); TSX IS +2 R/yr (p 0.11); TSX OOS +3 R/yr (p 0.10); US IS +4 R/yr (p 0.07); US OOS -1 R/yr (p 0.55)
  - Also run: S53_US
  - Also run: S53_HO

### S54 - Indicator stack: 2 of 3 of Parabolic SAR, Force Index(13), MACD bullish in an uptrend  [KEPT (weak)]
- Sources: Adam Khoo (1 refs). Taught on: US stocks
- Rule: In an uptrend, at least 2 of 3 (SAR dots below price, Force Index 13 > 0, MACD > signal) are bullish
- Ladder: 1) uptrend (MAs) -> 2) 2 of 3 bullish -> or 1 of 3 + bullish candle
- Code: ta2/strategies (see EVIDENCE there). Variations below were tested and NOT chosen.
- S54: 192 configs graded. Funnel (main fees): 192 -> 192 -> 96 -> 90 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: signals_needed: one_candle, three, two; gate: 200MA, none, slope, volume; target: 2R, flip; entry: close, next_open; buf: 0.1, 0.5
  - as taught (2 of 3, MA uptrend, next open, 2R) (long): IS 3353 tr, +0.15R, edge +0.03; OOS 2238 tr, +0.06R, edge -0.04
  - as traded (2 of 3, MA uptrend, indicator flip) (long): IS 4891 tr, +0.04R, edge +0.05; OOS 3265 tr, +0.04R, edge +0.05
  - taught alternative (1 plus candle, 2R) (long): IS 3768 tr, +0.13R, edge +0.02; OOS 2503 tr, +0.08R, edge -0.04
  - True edge, skill vs random twins (S54):
    - IS pick 1: signals_needed=two|gate=slope|flip|L|next_open|buf0.5: TSX IS +14 R/yr (p 0.00); TSX OOS +12 R/yr (p 0.05); US IS +0 R/yr (p 0.47); US OOS +17 R/yr (p 0.09)
    - IS pick 2: signals_needed=two|gate=none|flip|L|next_open|buf0.5: TSX IS +16 R/yr (p 0.00); TSX OOS +15 R/yr (p 0.03); US IS +4 R/yr (p 0.30); US OOS +18 R/yr (p 0.09)
    - IS pick 3: signals_needed=two|gate=volume|flip|L|next_open|buf0.5: TSX IS +10 R/yr (p 0.00); TSX OOS +3 R/yr (p 0.28); US IS +4 R/yr (p 0.28); US OOS +7 R/yr (p 0.21)
    - as taught (2 of 3, MA uptrend, next open, 2R): TSX IS +6 R/yr (p 0.15); TSX OOS -11 R/yr (p 0.89); US IS -4 R/yr (p 0.62); US OOS -21 R/yr (p 0.89)
    - as traded (2 of 3, MA uptrend, indicator flip): TSX IS +15 R/yr (p 0.01); TSX OOS +18 R/yr (p 0.03); US IS +9 R/yr (p 0.20); US OOS +22 R/yr (p 0.08)
    - taught alternative (1 plus candle, 2R): TSX IS +4 R/yr (p 0.29); TSX OOS -10 R/yr (p 0.85); US IS -3 R/yr (p 0.56); US OOS -31 R/yr (p 0.96)

### S55 - EMA stack / crossover trend (9/21/55 stack, 50/200 EMA, 7/30 MA, price x 50 EMA)  [KEPT (strong)]
- Sources: Booming Bulls, Power of Stocks (4 refs). Taught on: Bank Nifty (BB), BTC (PoS), stocks (V/M)
- Rule: Fast EMA crosses above slow EMA (or 9>21>55 all pointing up)
- Ladder: 1) base cross/stack -> 2) hold until price breaks the 9 (or 21 / 50) EMA -> 3) skip choppy markets -> 4) after 2-3 stops in a row, box the range and don't trade inside (zSMDeXlJCvk)
- Code: ta2/strategies (see EVIDENCE there). Variations below were tested and NOT chosen.
- S55: 512 configs graded. Funnel (main fees): 512 -> 512 -> 194 -> 182 -> 2 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: ma_set: cross20_50, cross50_200, cross9_21, stack9_21_55; gate: clear, clear+slope, none, slope; target: ema21, ema50, ema9, reverse_cross; entry: close, next_open; buf: 0.1, 0.5
  - as taught (daily 9/21/55 rising stack, exit EMA9) (long): IS 4147 tr, +0.01R, edge +0.06; OOS 2673 tr, -0.02R, edge +0.01
  - as traded (daily 9/21 cross, exit EMA21) (long): IS 2059 tr, +0.05R, edge +0.09; OOS 1381 tr, +0.08R, edge +0.10
  - 50/200 cross (daily, exit EMA50) (long): IS 395 tr, +0.09R, edge +0.12; OOS 334 tr, +0.15R, edge +0.14
  - True edge, skill vs random twins (S55):
    - 50/200 cross (daily, exit EMA50): TSX IS +3 R/yr (p 0.11); TSX OOS +5 R/yr (p 0.24); US IS +2 R/yr (p 0.22); US OOS +5 R/yr (p 0.14)
    - IS pick 1: ma_set=stack9_21_55|gate=none|ema9|L|next_open|buf0.5: TSX IS +16 R/yr (p 0.00); TSX OOS +3 R/yr (p 0.30); US IS +1 R/yr (p 0.45); US OOS +8 R/yr (p 0.25)
    - IS pick 2: ma_set=stack9_21_55|gate=slope|ema9|L|next_open|buf0.5: TSX IS +16 R/yr (p 0.00); TSX OOS +3 R/yr (p 0.30); US IS +1 R/yr (p 0.45); US OOS +8 R/yr (p 0.25)
    - IS pick 3: ma_set=cross9_21|gate=none|ema9|L|next_open|buf0.5: TSX IS +8 R/yr (p 0.00); TSX OOS +8 R/yr (p 0.01); US IS +8 R/yr (p 0.02); US OOS +14 R/yr (p 0.01)
    - as taught (daily 9/21/55 rising stack, exit EMA9): TSX IS +14 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.27); US IS +5 R/yr (p 0.25); US OOS +11 R/yr (p 0.21)
    - as traded (daily 9/21 cross, exit EMA21): TSX IS +11 R/yr (p 0.00); TSX OOS +15 R/yr (p 0.00); US IS +17 R/yr (p 0.00); US OOS +26 R/yr (p 0.00)

### S56 - 55 EMA break + retest entry (4h) with four exit models  [KEPT (weak)]
- Sources: Booming Bulls (1 refs). Taught on: Indian stocks (Tata Steel, Zeel)
- Rule: A 4h candle closes across the 55 EMA (or touches within ~1% and turns)
- Ladder: 1) trigger close across 55 EMA -> 2) retest of the 55 EMA without closing back through + strong-body candle -> enter; close back through cancels -> 3) monthly Fib pivot retest can substitute -> 4) choose ONE exit model and keep it: fixed 1:2 / monthly pivot R3-S3 / trail EMA13 / exit on 4h close through EMA55
- Code: ta2/strategies (see EVIDENCE there). Variations below were tested and NOT chosen.
- S56: 864 configs graded. Funnel (main fees): 864 -> 864 -> 354 -> 281 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: ema_pair: ema34_8, ema50_20, ema55_13; tolerance: 0.5, 1.0, 2.0; candle: directional, strong, strong+slope; target: 2R, ema_main, ema_trail, pivot; entry: close, next_open; buf: 0.1, 0.5
  - as taught (daily 55/13, 1% strong retest, 2R) (long): IS 818 tr, -0.01R, edge +0.06; OOS 467 tr, -0.04R, edge -0.04
  - as traded (daily 55/13, 1% directional retest, 2R) (long): IS 2138 tr, -0.14R, edge -0.00; OOS 1403 tr, -0.15R, edge -0.03
  - EMA13 exit (daily strong retest) (long): IS 825 tr, +0.15R, edge +0.29; OOS 475 tr, +0.02R, edge +0.07
  - EMA55 exit (daily strong retest) (long): IS 825 tr, +0.65R, edge +0.66; OOS 475 tr, +0.15R, edge +0.18
  - monthly Fibonacci R3/S3 (daily strong retest) (long): IS 800 tr, +0.23R, edge +0.14; OOS 461 tr, +0.01R, edge -0.08
  - True edge, skill vs random twins (S56):
    - EMA13 exit (daily strong retest): TSX IS +15 R/yr (p 0.08); TSX OOS +4 R/yr (p 0.26); US IS +18 R/yr (p 0.00); US OOS +25 R/yr (p 0.00)
    - EMA55 exit (daily strong retest): TSX IS +34 R/yr (p 0.04); TSX OOS +10 R/yr (p 0.12); US IS +21 R/yr (p 0.03); US OOS +26 R/yr (p 0.04)
    - IS pick 1: ema_pair=ema34_8|tolerance=2|candle=strong|ema_trail|L|next_open|buf0.5: TSX IS +12 R/yr (p 0.00); TSX OOS +11 R/yr (p 0.03); US IS +11 R/yr (p 0.04); US OOS +15 R/yr (p 0.04)
    - IS pick 2: ema_pair=ema34_8|tolerance=2|candle=strong+slope|ema_trail|L|next_open|buf0.5: TSX IS +12 R/yr (p 0.00); TSX OOS +11 R/yr (p 0.03); US IS +11 R/yr (p 0.04); US OOS +15 R/yr (p 0.04)
    - IS pick 3: ema_pair=ema50_20|tolerance=1|candle=directional|ema_main|L|next_open|buf0.5: TSX IS +44 R/yr (p 0.00); TSX OOS +43 R/yr (p 0.01); US IS +11 R/yr (p 0.21); US OOS +65 R/yr (p 0.01)
    - as taught (daily 55/13, 1% strong retest, 2R): TSX IS +3 R/yr (p 0.19); TSX OOS -2 R/yr (p 0.66); US IS +6 R/yr (p 0.14); US OOS -1 R/yr (p 0.54)
    - as traded (daily 55/13, 1% directional retest, 2R): TSX IS -0 R/yr (p 0.52); TSX OOS -5 R/yr (p 0.73); US IS -3 R/yr (p 0.62); US OOS +6 R/yr (p 0.30)
    - monthly Fibonacci R3/S3 (daily strong retest): TSX IS +7 R/yr (p 0.10); TSX OOS -4 R/yr (p 0.71); US IS +7 R/yr (p 0.17); US OOS -0 R/yr (p 0.52)

### S57 - News gap-and-go / pre-market-high breakout scalp (US stocks)  [NOT TESTED]
- Sources: Adam Khoo (2 refs). Taught on: US small/mid caps
- Rule: A stock gapping > 5% on news breaks its pre-market high (or makes its first 1-min pullback) after the open
- Ladder: 1) pre-market scan: gap > 5%, price > $1.50, news (earnings/upgrade), rank by volume; skip acquisition targets -> 2) consolidation just under pre-market high (skip if extended) -> 3) first 1m pullback/pin bar -> 4) done within ~30 min
- Why not tested: Not tested. | Type: Entry. Needs pre-market + 1m data and news; few TSX gappers. | Sources: 2 videos/docs from Adam Khoo. Ease of coding 2/3. Raw candidates: c097, c119.

### S58 - Indian index option-selling structures (trend-first strangle, holiday theta, inside-range straddle, after 3 down weeks)  [NOT TESTED]
- Sources: Power of Stocks (9 refs). Taught on: Bank Nifty / Nifty / BTC options
- Rule: Sell index options at swing levels after a defined condition (trend move first, holiday ahead, open inside yesterday's range, 3 down weeks)
- Ladder: Variants: trend-first strangle (>=1000-1500 Bank Nifty pts in first 7 days of month -> sell option against trend at last swing, add other leg at 50% retracement, N8HX17nEhKM); holiday theta strangle at last U-turn swings, fixed ~100 pt target (dL8hUocGwlI); sell when price opens inside prior day range, switch to buying after 12:30 (DG4mIaiyYbo); after 3 down weeks sell call at ~70-80% of last big 
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Not transferable: Indian index options, India margin rules. Kept for completeness; the price conditions (3 down weeks -> pause) could be tested on TSX week

### S59 - Expiry-day and event-day timing setups (India)  [NOT TESTED]
- Sources: Power of Stocks (6 refs). Taught on: Bank Nifty / Nifty
- Rule: Use the day's structure (expiry, budget, Muhurat) to decide when to sell premium and when to buy breakouts
- Ladder: Tue-Wed inside 200-250 pt box -> Thursday expiry breakout, hold 1:3-1:4 (8ehGFSaqpDs); budget days chop until ~12:00, then trade the 11:45-12:00 candle break (3GK-FmzBdTg, MbxBa0N0wBw); expiry ATM premium at 9:16 <150 = trend day, >200 = chop (7cGK_Ouaucg); Muhurat: skip first 5m candle, trade 2nd candle break (qfUWsMKlhV0)
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. India-specific events and expiries -> not transferable. "Big event: wait until midday" could be tested on TSX around BoC/FOMC days. | Sources: 6 videos/doc

### S60 - US options income & defined-risk structures (cash-secured put, covered call, bull put spread, call back-ratio)  [NOT TESTED]
- Sources: Adam Khoo, Power of Stocks (12 refs). Taught on: US stocks/ETFs (AK); Indian holdings (PoS)
- Rule: Sell premium on quality stocks/ETFs when implied volatility is high, at technically chosen strikes
- Ladder: 1) IV rank/percentile >= 30 (IBKR) or > 50 (CSP video) -> 2) chart first: uptrend, strong support or deeply oversold -> 3) structure: CSP at desired buy price 30-45 DTE; covered call OTM ~30 DTE above resistance, only after a 5-10% pullback, never at ATH (s2f_6bXeWzU); bull put 30-45 DTE short 20-28 delta, $5 wide, credit >= $1 -> 4) cut bull put at short strike
- Why not tested: Not tested. | Type: Entry. Partly taught on Indian/forex/gold markets - check transfer. Needs options history; relevant to Nik's advisor-track knowledge more than Phase 2. | Sources: 8 videos/docs from Adam Khoo, Power of Stocks. Ease of coding 1/3. Raw candidates

### S61 - PoS 1-minute opening scalps (traffic light, 1-min range after momentum leg, pullback-candle break, last swing beyond prior close)  [NOT TESTED]
- Sources: Power of Stocks (6 refs). Taught on: Bank Nifty options
- Rule: In the first hour, trade the break of a small 1-min structure (first opposite-colour candle pair, tight 3-4 candle range, single pullback candle)
- Ladder: Traffic light: ignore 9:15 candle; first red-green/green-red pair; break of pair H/L; skip pair if range > 100 pts; max 2 on 1m then 5m pair; 3 stops = day over (djC2hSdNo74). 1-min range: initial momentum leg, 3-4 candle tight range by bodies, break in leg direction, 1 trade/day (946OTXTWz0k). Continuation: 2-3 continuation candles, 1 opposite pullback candle, enter on its break (Qofnwi8BpWk). La
- Why not tested: Not tested. | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. 1-min data; Indian index options. Low transfer value. | Sources: 6 videos/docs from Power of Stocks. Ease of coding 2/3. Raw candidates: c176, c178, c182, 

### S62 - Filter: Intraday time-of-day and weekday filters (overlay)  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (6 refs). Taught on: Nifty / Bank Nifty / gold
- Rule: Only take (or only fade) breakouts in specific session windows / weekdays
- Ladder: 1) skip first 15 min (3f7TFHpHrFc) / first 30 min (Lb4yel3nCws) -> 2) 9:15-12:00 breakouts mostly fail (fade), 13:30-15:30 breakouts holding into the close mostly work (2a6Hy0FKPZI, p1NwYE35IRo) -> 3) 10:30-12:30 "no man's land" -> 4) slice any strategy by entry time and weekday, size up best slots (z_D7hYoGILw)
- Why not tested: Not tested. | Type: Filter. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. High data-mining risk; only accept if it holds out-of-sample. | Sources: 6 videos/docs from Booming Bulls, Power of Stocks. Ease of coding 3/3. Raw candid

### S63 - Filter: Intraday ATR-consumption / distance-travelled filter (overlay)  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (3 refs). Taught on: Gold, BTC, Indian stocks
- Rule: Before a trigger, check how much of the average daily range is already used (or how far price already ran to the trigger)
- Ladder: 1) ATR used: 1h ATR(24) or prior-day range/2; if mostly used -> look for reversals, else breakouts (5glwOHR6nEA) -> 2) skip/downsize if >= 1-2% (or >1% of ADR) already travelled before the trigger; size up if < 0.25-0.5% (CRVk7xHYb8M) -> 3) for current-day H/L fades need 70-80% of daily ATR used (IOBoaM71MUA)
- Why not tested: Not tested. | Type: Filter. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Daily version (open within ~1% of trigger) is a rung of S09. | Sources: 3 videos/docs from Booming Bulls, Power of Stocks. Ease of coding 3/3. Raw candida

### S64 - Filter: Calendar seasonality (September weakness; Sep-Feb correction start; month-start volatility)  [KEPT (weak)]
- Sources: Adam Khoo, Power of Stocks (2 refs). Taught on: S&P 500 (AK); Nifty (PoS)
- Rule: Expect weaker returns in September (and around specific calendar windows)
- Ladder: 1) September avg -0.6%, up 45% since 1945 -> 2) election-year Sep-Oct chop, rally into year-end -> 3) PoS: most big corrections started Sep-Feb (CxeYslnbq0k, not a separate candidate) -> 4) PoS month structure: volatility clusters in days 1-10 (PoWMz50wxCc)
- Verdict: Kept as weak (S64 skip-September only). Rejected parts: 'sell in May' (skip May-Oct: -4.3%/yr OOS), Sep-Feb correction claim (33% of corrections), days 1-10 volatility.
- Code: ta2/strategies (see EVIDENCE there). Variations below were tested and NOT chosen.

### S65 - Macro / sentiment regime (VIX spikes, fund cash > 5%, earnings yield vs bond yield, breadth, price-news divergence)  [NOT TESTED]
- Sources: Adam Khoo, Booming Bulls (5 refs). Taught on: US market
- Rule: Use sentiment/macro extremes as a regime input for buying (fear) or trimming (complacency)
- Ladder: 1) VIX spike / record bearishness = buy quality (LSwsppvXnb4, uCNLZVoppRc) -> 2) fund-manager cash > 5% = bearish crowd -> contrarian buy (URkXUuVYwiI) -> 3) S&P earnings yield > 10-yr yield = stocks cheap (ezsA1CEr6Us) -> 4) breadth: McClellan +/-100, Arms 10d > 1.2 oversold [M] -> 5) stock rising on bad news = strong (UAmqu_au61M)
- Why not tested: Not tested. | Type: Entry. VIX is free daily; survey, EPS and breadth data are not -> B. VIX-spike rule could be tested as part of S35. | Sources: 5 videos/docs from Adam Khoo, Booming Bulls, TA books/papers. Ease of coding 1/3. Raw candidates: c059, c079, c102, c

### S66 - Baseline: Passive index buy-and-hold / DCA (benchmark)  [NOT TESTED]
- Sources: Adam Khoo, Power of Stocks (3 refs). Taught on: Dow, S&P, Nifty ETFs
- Rule: Buy the index ETF and hold (or buy a fixed amount at fixed intervals)
- Ladder: 1) lump-sum buy and hold -> 2) DCA monthly/daily (cgIb6K6eg7Q) -> 3) dividends reinvested
- Why not tested: ALREADY USED as the benchmark in tsx-backtest-results.md (dividend-adjusted B&H beat every rule in >90% of TSX 60 stocks). | Type: Baseline. Partly taught on Indian/forex/gold markets - check transfer. Every swing/position strategy is graded against this (dividend-adjusted XIU/XIC). | Sources: 3 videos/docs from Adam Khoo, Power of Stocks. Ease of coding 3/3. Priority 101+

### S67 - Static risk-balanced multi-asset mix with annual rebalance  [REJECTED]
- Sources: Adam Khoo, Power of Stocks (3 refs). Taught on: US ETFs; Indian assets
- Rule: Hold fixed weights across stocks, bonds, gold, commodities and rebalance yearly
- Ladder: 1) AK all-weather: 30 SPY / 40 TLT / 15 IEI / 8 GLD / 8 DBA (6MdYGNO6uQ0) -> 2) AK variant: 24 SPY / 20 EEM / 40 TLT / 8 GLD / 8 DBC (OQuLtyV73gc) -> 3) PoS: 60/20/10/10 (equity/real estate/gold/cash, age 31) or 40 eq/30 FI/20 gold/10 cash (w4MF8LB0ra8) -> 4) annual rebalance
- Verdict: UNTESTABLE with current data (no bond/gold ETFs; 'mix' = 62% cash). Needs XBB/CGL-type series.

### S68 - Rules-based index dip buying (buy after red periods; tranches at supports; ETF vs stock switch)  [REJECTED]
- Sources: Adam Khoo, Power of Stocks (3 refs). Taught on: Nifty ETFs (PoS); SPY/QQQ (AK)
- Rule: Buy index ETFs only after a red period (or at predefined support levels) instead of on a calendar
- Ladder: 1) small amounts: buy only when the monthly candle closes red; weekly/daily for larger amounts (V2E7QgBcp6k) -> 2) AK: buy 1/4 tranches at 4 predefined weekly support/MA levels (U5wsngHknjI) -> 3) PoS: stocks when index at ATH, ETFs when index 5-10% off top (3nKkjwipEOM) -> 4) average only indices, never single stocks
- Verdict: Claim false: red-month / dip deposit timing = monthly SIP (IRR -0.14 / -0.24 pts/yr).

### S69 - Fundamental quality & red-flag screen (feeds the equity tool)  [NOT TESTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (11 refs). Taught on: US/HK/SG/Indian stocks
- Rule: Only consider businesses with consistent revenue/profit/CFO growth, high ROE/ROIC, conservative debt, and no red flags
- Ladder: 1) rising revenue, net income, CFO -> 2) ROE/ROIC >= 12-15% -> 3) red flags = hard fail: negative CFO/FCF, dividends > FCF, receivables >> revenue growth, debt/EBITDA > 3, interest/CFO > 30%, current ratio < 1, net margin < 0.5% -> 4) valuation vs peers (P/E, P/B vs sector) -> 5) category map (defensive/predictable = hold; cyclical/growth = trade the trend) -> 6) sell trigger: multi-year revenue/F
- Why not tested: Not tested as a strategy (belongs to the equity tool's scoring, not Phase 2 TA backtests). | Type: Entry. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Needs historical fundamentals (not free daily price data) -> B. Already reflected in the tool methodology notes. | Sources: 11 videos/docs from Adam Khoo, 

### S70 - Intrinsic-value discount buying and IV-based selling  [NOT TESTED]
- Sources: Adam Khoo, Booming Bulls (11 refs). Taught on: US/China stocks
- Rule: Buy quality businesses when price is well below intrinsic value (DCF/DNI/mean P/B by company type)
- Ladder: 1) method by company type (DCF compounders, mean P/E cyclicals, DNI insurers, mean P/B banks) -> 2) buy >= 20% below IV (30-60% in 36B_9V3sMBE) -> 3) buy in 1/4 tranches at technical supports -> 4) bear/base/bull IV; buy below bear case -> 5) sell only if moat breaks, better use of cash, or price > 100% above IV (sell in quarters)
- Why not tested: Not tested. | Type: Entry. This is the equity tool's target-price logic, not a TA strategy. | Sources: 11 videos/docs from Adam Khoo, Booming Bulls. Ease of coding 1/3. Raw candidates: c009, c049, c282, c300, c100, c075.

### S71 - Dividend growth and yield-trap screen  [NOT TESTED]
- Sources: Adam Khoo (2 refs). Taught on: US/Singapore stocks
- Rule: Own stocks with consistently rising dividends per share and avoid high yields caused by falling prices/DPS
- Ladder: 1) DPS rising 5-10 yrs -> 2) yield >= 4-5% (cash-cow basket) -> 3) growing earnings/FCF, low leverage, interest/CFO < 30% -> 4) defensive sectors only, exclude cyclicals -> 5) exclude if DPS fell over 5 yrs
- Why not tested: Not tested. | Type: Entry. Feeds the tool's 10% dividend parameter; Canadian dividend stocks are the obvious universe. | Sources: 2 videos/docs from Adam Khoo. Ease of coding 2/3. Raw candidates: c003, c099.

### S72 - Price-first momentum investing: monthly breakout + 2-3 strong monthly closes, 20% stop, no target  [REJECTED]
- Sources: Power of Stocks (5 refs). Taught on: Indian stocks (Mazagon Dock example)
- Rule: Buy stocks showing a monthly-chart breakout plus 2-3 months of strong closes
- Ladder: 1) shortlist fundamentally OK names -> 2) monthly breakout + 2-3 strong closes -> 3) meaningful size -> 4) exit if -20% (10% or 5% if risk-averse) or below last swing low -> 5) re-enter if it reclaims entry; never average down; time limit ~3 yrs, take initial capital out after a double
- Verdict: No skill: 13.4%/15.4%/yr vs XIU, but random picks with the same structure do as well (survivorship + concentration).

### S73 - Support/resistance range mean reversion (buy fresh support, sell fresh resistance, never the middle)  [REJECTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (15 refs). Taught on: Forex (AK), Indian stocks (BB, PoS)
- Rule: In a range, buy a bullish reaction candle at a qualified support zone (sell at resistance)
- Ladder: 1) level qualification: >= 3 touches (AK/BB) vs first retest strongest and 3+ touches weak (PoS) -> 2) zone drawn by bodies (BB, PoS) -> 3) regime: MAs criss-crossing / ranging (C06JMxI6Tsg) -> 4) reaction candle (power/LPR, green from demand) -> 5) never trade the middle of the range (_R7b3VIFbzE) -> 6) stop beyond level + buffer 2x ATR (C06JMxI6Tsg) -> 7) target: book in front of once-hit levels
- Verdict: No edge (best p 0.09): longs profitable ~96% but beat random by only ~+0.02R. Watch: >=3 touches + bounce>=5% + ADX<20; ADX<20 the one dial that helps both windows.
- S73: 2,592 configs graded. Funnel (main fees): 2592 -> 2592 -> 1247 -> 788 -> 126 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: zone: 0.5, 1.0, 2.0; touches: 3+, any, first; bounce: 10, 3, 5, any; regime: adx<20, none; target: 1.5R, 2R, opp; entry: close, next_open; buf: 0.5, 1.0, 2.0
  - as taught AK/BB (>=3 touches, bounce>=5%, ADX<20, strong candle, opp target, stop 2 ATR, at close) (long): IS 492 tr, +0.05R, edge -0.04; OOS 324 tr, +0.10R, edge +0.07
  - as taught PoS (first retest, bounce>=5%, strong candle, opp target, stop 2 ATR, at close) (long): IS 1736 tr, +0.02R, edge -0.04; OOS 1117 tr, +0.10R, edge +0.03
  - as traded (any touch, 2R, stop 1 ATR, next open) (long): IS 3652 tr, +0.11R, edge +0.01; OOS 2519 tr, +0.08R, edge +0.03
  - True edge, skill vs random twins (S73):
    - IS pick 1: zone=1.0|touches=first|bounce=any|regime=adx<20|2R|L|next_open|buf0.5: TSX IS +14 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.24); US IS +3 R/yr (p 0.38); US OOS -1 R/yr (p 0.52)
    - IS pick 2: zone=0.5|touches=first|bounce=any|regime=adx<20|2R|L|next_open|buf0.5: TSX IS +11 R/yr (p 0.00); TSX OOS +11 R/yr (p 0.07); US IS -2 R/yr (p 0.60); US OOS -3 R/yr (p 0.61)
    - IS pick 3: zone=0.5|touches=3+|bounce=3|regime=adx<20|2R|L|next_open|buf2.0: TSX IS +5 R/yr (p 0.01); TSX OOS +1 R/yr (p 0.42); US IS +2 R/yr (p 0.24); US OOS -1 R/yr (p 0.54)
    - as taught AK/BB (>=3 touches, bounce>=5%, ADX<20, strong candle, opp target, stop 2 ATR, at close): TSX IS -1 R/yr (p 0.76); TSX OOS +2 R/yr (p 0.16); US IS -3 R/yr (p 0.90); US OOS +0 R/yr (p 0.44)
    - as taught PoS (first retest, bounce>=5%, strong candle, opp target, stop 2 ATR, at close): TSX IS -4 R/yr (p 0.90); TSX OOS +3 R/yr (p 0.28); US IS +3 R/yr (p 0.37); US OOS -1 R/yr (p 0.53)
    - as traded (any touch, 2R, stop 1 ATR, next open): TSX IS +3 R/yr (p 0.33); TSX OOS +8 R/yr (p 0.26); US IS -4 R/yr (p 0.59); US OOS +3 R/yr (p 0.44)
  - Also run: S73_US

### S74 - Filter: Higher-timeframe trend alignment filter (triple timeframe / top-down)  [NOT TESTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (7 refs). Taught on: US stocks (AK); forex, Indian stocks (BB, PoS)
- Rule: Only trade in the direction of the higher-timeframe trend (monthly -> weekly -> daily, or 4h -> 1h -> 15m)
- Ladder: 1) long-term (5-10 yr), medium (6m-2yr), short (1-3m) trends all up for short-term traders (jjJXW2Kgjpg) -> 2) levels from the higher TF only, setups on the lower TF (YKk2WmtZNS0) -> 3) same level on 4h and 1h = confluence (bYIHPBm1CIY) -> 4) weekly idea, hourly stop to keep 1:2 (Tzjgn0iDIk8)
- Why not tested: Not tested. | Type: Filter. Partly taught on Indian/forex/gold markets - check transfer. Test as a rung on S09/S19/S04: weekly 50>150 (or weekly close > 40-week MA) required. | Sources: 7 videos/docs from Adam Khoo, Booming Bulls, Power of Stocks. Ease of coding 3

### S75 - Filter: Monthly-candle index regime rules (follow-through, big-wick range month, bearish month -> sell early next month, crash vs correction)  [NOT TESTED]
- Sources: Power of Stocks (10 refs). Taught on: Nifty, Bank Nifty, gold, BTC, Nasdaq
- Rule: Read the last monthly (weekly) candle on the index to set the next month's bias
- Ladder: 1) strong bearish monthly close -> sell the first 5-10 days of next month (NGebQLMGTLs) -> 2) monthly big two-sided wick, small body -> next month ranges, no positional trend trades (OMijq9P8Tho) -> 3) monthly bearish engulfing at a top -> 1-3 months weakness; bias stays bearish until 50% of the engulfing candle is reclaimed (3nKkjwipEOM) -> 4) big red candle with a second close below = follow-thr
- Why not tested: Not tested. | Type: Filter. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Each rule is a simple monthly-bar statistic -> test as "next-month return conditional on candle type" on TSX/S&P. | Sources: 10 videos/docs from Power of 

### S76 - Filter: ADX regime filter (trend vs range)  [NOT TESTED]
- Sources: Booming Bulls (4 refs). Taught on: Nifty (BB); stocks/futures (Murphy)
- Rule: ADX(14) above ~20-25 and rising = trending; below 20 or falling = sideways
- Ladder: 1) ADX < 20 -> no breakout trades -> 2) rising ADX through 20-25 -> take breakouts -> 3) falling ADX (2-3 pts per candle) = sideways day (6UvWqu-c1Ic) -> 4) +DI/-DI cross with ADX > 25 = trend entry [M] (BB calls DI crosses weak)
- Why not tested: Not tested. | Type: Filter. Partly taught on Indian/forex/gold markets - check transfer. Cheap, widely taught filter; test on S09/S10 (does ADX>20 raise PF?). | Sources: 4 videos/docs from Booming Bulls, TA books/papers. Ease of coding 3/3. Priority 101+ = filters

### S77 - Impulse pullback (Adam Khoo): MA/MACD cross, pullback flushes early buyers, enter above latest swing high  [REJECTED]
- Sources: Adam Khoo (1 refs). Taught on: US stocks, forex
- Rule: After an EMA/MACD trend-change cross, price pulls back (trapping early breakout buyers) and then breaks the latest swing high
- Ladder: 1) 6/18 EMA (and 50 EMA, 200 SMA) cross + MACD confirmation -> 2) pullback -> 3) break of the latest swing high in trend direction
- Verdict: No edge: long profitable 21% IS / 64% OOS, median edge -0.03/+0.06R.
- S77: 384 configs graded. Funnel (main fees): 384 -> 384 -> 40 -> 19 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: cross: 6/18, 9/21; confirmation: MACD, MACD+50, MACD+50+200, none; pullback: any, half ATR, two bars; target: 2.5R, 2R; entry: close, next_open; buf: 0.1, 0.5
  - as taught (long): IS 1341 tr, -0.00R, edge +0.04; OOS 819 tr, +0.04R, edge +0.09
  - as traded (long): IS 1753 tr, -0.05R, edge +0.01; OOS 1106 tr, -0.01R, edge +0.07
  - True edge, skill vs random twins (S77):
    - IS pick 1: cross=6/18|confirmation=MACD+50+200|pullback=half ATR|2R|L|next_open|buf0.1: TSX IS +3 R/yr (p 0.22); TSX OOS +10 R/yr (p 0.03)
    - IS pick 2: cross=6/18|confirmation=MACD|pullback=two bars|2R|L|close|buf0.1: TSX IS +3 R/yr (p 0.24); TSX OOS -1 R/yr (p 0.55)
    - IS pick 3: cross=6/18|confirmation=MACD+50+200|pullback=any|2.5R|L|next_open|buf0.1: TSX IS +3 R/yr (p 0.24); TSX OOS +9 R/yr (p 0.11)
    - as taught: TSX IS +3 R/yr (p 0.24); TSX OOS +9 R/yr (p 0.11)
    - as traded: TSX IS +1 R/yr (p 0.37); TSX OOS +9 R/yr (p 0.12)

### S78 - Big daily candle (5-7%) then pause -> fade the next move  [REJECTED]
- Sources: Power of Stocks (1 refs). Taught on: Indian stocks
- Rule: After an unusually large daily candle (5-7% vs a 3-4% average), the next candle usually pauses or retraces
- Ladder: 1) daily range/return >= 5-7% -> 2) next day pause/retrace -> 3) fade
- Verdict: 'Works 60-70%' true (69% wins) but money false: avgR +0.00/-0.04R; 0 of 1,440 configs PF 1.3. S78X (exit panel): no edge, watch time5 fade (RW p 0.11).
- S78: 1,440 configs graded. Funnel (main fees): 1440 -> 1365 -> 94 -> 88 -> 0 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: big_rule: range2, range3, ret4, ret5, ret7; timing_family: now, pause; strong_gate: False, True; volume_gate: False, True; target: 1.5R, 2R, opp; entry: close, next_open; buf: 0.1, 0.5, 1.0
  - as taught (long): IS 470 tr, -0.12R, edge +0.13; OOS 229 tr, -0.16R, edge +0.04
  - as traded (long): IS 643 tr, -0.25R, edge +0.08; OOS 442 tr, -0.26R, edge +0.01
  - True edge, skill vs random twins (S78):
    - IS pick 1: big_rule=ret4|timing_family=pause|strong_gate=False|volume_gate=False|opp|L|close|buf0.5: TSX IS +12 R/yr (p 0.00); TSX OOS +7 R/yr (p 0.01)
    - IS pick 2: big_rule=ret4|timing_family=pause|strong_gate=True|volume_gate=False|opp|L|close|buf0.5: TSX IS +12 R/yr (p 0.00); TSX OOS +6 R/yr (p 0.03)
    - IS pick 3: big_rule=ret4|timing_family=pause|strong_gate=False|volume_gate=False|opp|L|close|buf1.0: TSX IS +8 R/yr (p 0.00); TSX OOS +3 R/yr (p 0.16)
    - as taught: TSX IS +4 R/yr (p 0.01); TSX OOS +1 R/yr (p 0.32)
    - as traded: TSX IS +3 R/yr (p 0.13); TSX OOS +1 R/yr (p 0.43)
- S78X: 432 configs graded. Funnel (main fees): 432 -> 432 -> 83 -> 80 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: setup: as taught, as traded, ret4_now, ret4_pause, ret4_pause_strong, ret4_pause_volume; big_rule: ret4; timing_family: now, pause; target: 2R, be1_2R, be1_3R, half1R_trail2atr, time10, time5, trail2atr, trail3atr, trail_ma20; entry: close, next_open; buf: 0.1, 0.5
  - as taught | 2R (long): IS 607 tr, +0.00R, edge +0.10; OOS 291 tr, +0.05R, edge +0.06
  - as taught | be1_2R (long): IS 612 tr, -0.02R, edge +0.11; OOS 293 tr, -0.02R, edge +0.04
  - as taught | be1_3R (long): IS 609 tr, -0.01R, edge +0.06; OOS 293 tr, +0.04R, edge +0.05
  - as taught | trail2atr (long): IS 612 tr, -0.03R, edge +0.05; OOS 293 tr, +0.01R, edge -0.05
  - as taught | trail3atr (long): IS 594 tr, +0.01R, edge +0.05; OOS 283 tr, +0.08R, edge -0.03
  - as taught | trail_ma20 (long): IS 617 tr, +0.05R, edge +0.11; OOS 296 tr, -0.11R, edge -0.18
  - as taught | half1R_trail2atr (long): IS 612 tr, -0.07R, edge +0.07; OOS 293 tr, -0.05R, edge -0.00
  - as taught | time5 (long): IS 615 tr, -0.04R, edge +0.02; OOS 297 tr, +0.01R, edge -0.03
  - as taught | time10 (long): IS 605 tr, +0.09R, edge +0.09; OOS 292 tr, +0.04R, edge +0.01
  - as traded | 2R (long): IS 770 tr, -0.18R, edge +0.01; OOS 519 tr, -0.20R, edge -0.06
  - as traded | be1_2R (long): IS 773 tr, -0.19R, edge +0.04; OOS 519 tr, -0.23R, edge -0.06
  - as traded | be1_3R (long): IS 772 tr, -0.21R, edge +0.01; OOS 518 tr, -0.17R, edge -0.03
  - True edge, skill vs random twins (S78X):
    - IS pick 1: setup=ret4_pause_strong|big_rule=ret4|timing_family=pause|time5|L|close|buf0.5: TSX IS +14 R/yr (p 0.00); TSX OOS +8 R/yr (p 0.08)
    - IS pick 2: setup=ret4_pause_strong|big_rule=ret4|timing_family=pause|half1R_trail2atr|L|close|buf0.5: TSX IS +11 R/yr (p 0.00); TSX OOS +5 R/yr (p 0.15)
    - IS pick 3: setup=ret4_pause|big_rule=ret4|timing_family=pause|be1_2R|L|close|buf0.1: TSX IS +12 R/yr (p 0.00); TSX OOS +6 R/yr (p 0.13)
    - as taught | 2R: TSX IS +4 R/yr (p 0.10); TSX OOS +2 R/yr (p 0.31)
    - as taught | be1_2R: TSX IS +4 R/yr (p 0.07); TSX OOS +1 R/yr (p 0.35)
    - as taught | be1_3R: TSX IS +2 R/yr (p 0.24); TSX OOS +2 R/yr (p 0.35)
    - as taught | half1R_trail2atr: TSX IS +3 R/yr (p 0.20); TSX OOS -0 R/yr (p 0.53)
    - as taught | time10: TSX IS +3 R/yr (p 0.25); TSX OOS +0 R/yr (p 0.46)
    - as taught | time5: TSX IS +1 R/yr (p 0.39); TSX OOS -1 R/yr (p 0.58)
    - as taught | trail2atr: TSX IS +2 R/yr (p 0.32); TSX OOS -2 R/yr (p 0.61)

### S79 - Baseline: Random-entry baseline with exit variants (PoS experiments)  [NOT TESTED]
- Sources: Power of Stocks (2 refs). Taught on: Reliance futures, Bank Nifty options
- Rule: Enter at a fixed time with no setup (or by coin toss) and compare exit rules
- Ladder: 1) Reliance futures bought every day at 9:18, Rs4 stop, exit 15:10 or at 1:1...1:5 targets (1NWjJNtZQa4) -> 2) coin toss at 9:30 for direction, stop Rs30, target 1:3, second trade only if first stopped (CfrFtoTzQo8)
- Why not tested: Partly: the Phase 2 method (claude/phase2-registry-prompt.md) already plans random-entry baselines with the same exits. | Type: Baseline. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Not a strategy to trade; it is the control group. Daily version: random entry days on TSX 60 with each strategy's stop/target. | Sources: 2 videos/docs 

### S80 - Overlay: fixed-fractional risk per trade and portfolio limits  [NOT TESTED]
- Sources: Adam Khoo, Power of Stocks (5 refs). Taught on: All
- Rule: Risk a fixed % of equity per trade; shares = (risk % x equity) / (entry - stop)
- Ladder: 1) 1% risk (max 2-3%) (AK) / 1-2% (BB) / 2% in 100-trade blocks, reset after doubling (PoS XMqkbOs-VXU) -> 2) target >= 2R (stocks), 1:3 option buying, 1:1 option selling (VN0WzCKiWcw) -> 3) total open risk <= 10%, <= 2 positions per sector, never 2 correlated trades -> 4) equal-weight entries, let winners run (locAdPua4cA)
- Why not tested: Not tested (tsx-backtest-results used one position, no sizing). | Type: Overlay. Apply to every Phase 2 test; compare 0.5/1/2%. | Sources: 5 videos/docs from Adam Khoo, Power of Stocks. Ease of coding 3/3. Priority 101+ = filters/overlays/baselines, applied together with the entry strategies rather than tested alon

### S81 - Overlay: daily loss circuit breaker (stop after 2-3 losses / daily loss cap / 20-day runway)  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (5 refs). Taught on: All intraday
- Rule: Stop trading for the day after N stop-losses or after a fixed daily loss
- Ladder: 1) 2 stops/day (BB, many videos) / 3 stops (PoS, -BCL990-HnQ) / 3 consecutive (PoS ljKKAuELyAc) -> 2) 4th trade allowed only if an earlier trade won -> 3) runway: capital/20 = daily loss cap split into 3 trades (fIS_NMTt-UE) -> 4) daily loss 5-6% max (BB 5tUHt4N05eM) vs 3% (Burns)
- Why not tested: Not tested. | Type: Overlay. Only meaningful for intraday strategies (B). | Sources: 4 videos/docs from Booming Bulls, Power of Stocks. Ease of coding 3/3. Raw candidates: c002, c191, c256.

### S82 - Overlay: exit rules - breakeven move, trailing, partial exits, book-and-re-enter  [NOT TESTED]
- Sources: Adam Khoo, Booming Bulls, Power of Stocks (9 refs). Taught on: All
- Rule: Same entries, different exits
- Ladder: Exit menu: fixed 1.5-2.5R; stop to BE at +1R (AK) / at 50% of the way (BB lYr7pBtCORs); trail after 80% of target; trail only after 1:1 (PoS VrD4JS74fYs) or 1:2 (NGebQLMGTLs); trail by structure (higher lows) for stocks; 20 EMA < 40 EMA exit; trail below 50 MA; daily close below 5 EMA (growth stocks); RSI > 70 take profit; opposite-candle trail; partial 80-90% at 1:2-1:3 + runner; book-and-re-ente
- Why not tested: Not tested. | Type: Overlay. Run as a fixed exit panel on the top bucket-A entries (like S56's four exits). | Sources: 9 videos/docs from Adam Khoo, Booming Bulls, Power of Stocks. Ease of coding 3/3. Priority 101+ = filters/overlays/baselines, applied together wi

### S83 - Overlay: equity-curve scaling (raise size only on a new equity high after a drawdown)  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (5 refs). Taught on: All
- Rule: Keep size constant through a winning streak; increase only after the account retraces and then reclaims its prior high
- Ladder: 1) constant size in streaks -> 2) wait for drawdown + recovery to new equity high -> 3) then raise size/capital (HgB5nVaudyc, d9PZBSn-WAs) -> 4) withdraw profits at doublings (PoS); reduce size after 3 winners (CfrFtoTzQo8) or in losing streaks (Paul Tudor Jones, EyB1jrXA7bk)
- Why not tested: Not tested. | Type: Overlay. Testable on any backtest equity curve vs fixed-fractional compounding. | Sources: 4 videos/docs from Power of Stocks. Ease of coding 3/3. Priority 101+ = filters/overlays/baselines, applied together with the entry strategies rather tha

### S84 - Overlay: overnight carry filter (hold overnight only with a profit cushion)  [NOT TESTED]
- Sources: Power of Stocks (2 refs). Taught on: Indian stocks/options
- Rule: Start every positional trade as an intraday trade; carry it overnight only if it closes in profit by a cushion
- Ladder: 1) entry intraday -> 2) close >= entry + 2-5% (89tvXCgFFAw) or >= 1:2 in profit (FkVwoRUogAg) -> carry; else exit at the close and re-enter later
- Why not tested: Not tested. | Type: Overlay. Taught on Indian index/stocks, forex, gold or crypto - transfer to TSX uncertain. Codeable on daily bars for breakout entries (entry at the level, check the close). | Sources: 2 videos/docs from Power of Stocks. Ease of coding 3/3. Pri

### S85 - Overlay: pyramiding into winners vs never averaging down  [NOT TESTED]
- Sources: Booming Bulls, Power of Stocks (5 refs). Taught on: All
- Rule: Add to a position only after it moves in your favour and offers a new entry with its own stop; never add to a loser
- Ladder: 1) half size on breakout, add half on the first pullback that holds (J-zciUEp5SM) / 75% on trendline break + 25% on first pullback (2nGrPAEN3vw) -> 2) add only after a pullback candle and resumption (wlcxfeKN2Ag) -> 3) every add-on gets its own stop; max 1-2 adds (Bmomq8bDQkw) -> 4) never average down (all three channels)
- Why not tested: Not tested. | Type: Overlay. Test half-in/half-on-retest vs all-in on S09 breakouts. | Sources: 5 videos/docs from Booming Bulls, Power of Stocks. Ease of coding 2/3. Priority 101+ = filters/overlays/baselines, applied together with the entry strategies rather tha

### S86 - Bollinger squeeze then breakout (and band-ride in uptrends)  [REJECTED]
- Sources: Power of Stocks (3 refs). Taught on: Indian stocks (PoS); generic [M]
- Rule: Bollinger Band width contracts (squeeze), then price closes outside the band
- Ladder: 1) squeeze (narrow bands) -> 2) close beyond band/range -> 3) weekly timeframe (PoS fa3Cgp6pnKA) -> 4) in uptrends price rides between upper band and 20 MA; close below the 20 MA warns [M] -> 5) skip if it gaps below the level
- Verdict: Classic collapse: long 100% profitable IS -> 17% OOS, median edge +0.10 -> -0.10R.
- S86: 360 configs graded. Funnel (main fees): 360 -> 360 -> 180 -> 173 -> 0 -> 0  (tested -> >=100 IS -> profitable -> beats random -> luck-corrected -> holds OOS)
  - Dials tested: squeeze: low120, p10_120, p10_250, p20_120, p20_250; gate: none, trend, volume; target: 2R, ma20, opposite_band; entry: close, next_open; buf: 0.1, 0.5
  - as taught (daily, six-month low, 2R) (long): IS 744 tr, +0.06R, edge +0.06; OOS 508 tr, -0.14R, edge -0.10
  - as traded (lowest 20%, band ride) (long): IS 1903 tr, +0.20R, edge +0.25; OOS 1294 tr, -0.06R, edge -0.10
  - True edge, skill vs random twins (S86):
    - IS pick 1: squeeze=p10_120|gate=volume|ma20|L|next_open|buf0.1: TSX IS +17 R/yr (p 0.00); TSX OOS -11 R/yr (p 0.91)
    - IS pick 2: squeeze=p10_120|gate=volume|ma20|L|close|buf0.1: TSX IS +17 R/yr (p 0.00); TSX OOS -4 R/yr (p 0.68)
    - IS pick 3: squeeze=p10_250|gate=volume|ma20|L|close|buf0.1: TSX IS +15 R/yr (p 0.00); TSX OOS -10 R/yr (p 0.91)
    - as taught (daily, six-month low, 2R): TSX IS +3 R/yr (p 0.16); TSX OOS -6 R/yr (p 0.90)
    - as traded (lowest 20%, band ride): TSX IS +29 R/yr (p 0.03); TSX OOS -15 R/yr (p 0.91)

---
## Humbled Trader (Shay) first wave — tested 2026-11-03 in ta2 (HT1, HT2, HT3)
Universe TSX60 (US100 cold check). Engine modes added for these: open entry (mode 2), order-price entry (mode 3), same-day exit.
Funnel per family = configs -> >=100 trades IS -> profitable -> beats random -> survives Romano-Wolf IS -> holds OOS (main fees 0.12%/side).
**DATA WARNING for any open-entry test:** Yahoo TSX opens before ~2005 are unreliable (open = day's low on 19% of all days 2000-04 vs 6% in US data). Buy/short-at-the-open ideas look great in the TSX IS window and collapse later or on US data. Judge open entries on US data or 2005+ only.

### HT1-fgd - First green day (buy-stop at prior close after >=2 red closes, gap-down open)  [REJECTED]
- Funnel: 100 -> 40 -> 11 -> 11 -> 2 -> 1. TSX survivor (fam=fgd|flt=big|next, >=5% drop in 5 days, exit next close): IS +0.05R edge +0.11; OOS +0.02R edge +0.08 (p .009).
- US cold: same config OOS -0.046R, edge +0.03 (p 0.20) -> fails. As taught (out at the close): IS +0.00R, OOS -0.02R.

### HT1-day2 - Day-2 reclaim of a 3%+ volume breakout day  [REJECTED]
- Funnel: 100 -> 20 -> 0. Too rare on large caps (188 trades IS best case) and negative: best IS -0.05R, OOS -0.11R.

### HT1-frd - First red day short (>=5 green closes, sell-stop at prior close)  [REJECTED]
- Funnel: 80 -> 40 -> 0. Timing beats random (edge +0.09 IS) but loses money: IS -0.07R, OOS -0.18R. Shorting large-cap strength loses to drift.

### HT1-bag - Bagholder short, large-cap analog (below 200 SMA, 1-3 day pop >= 10%)  [REJECTED]
- Funnel: 80 -> 32 -> 1 -> 1 -> 0. Best: IS -0.03R edge +0.06 (p_rw .27), OOS -0.03R. Real version needs small caps (< $300M) - untestable on TSX60.

### HT2-idxdip - Index gap-down dip buy (Shay's "A+" setup)  [REJECTED]
- Funnel: 144 -> 72 -> 12 -> 12 -> 0. Best: IS -0.10R edge +0.07 (p_rw .04); OOS -0.18R edge -0.02. Gap fill target too small for costs.

### HT2-gdcont - Gap-down continuation short  [REJECTED]
- Funnel: 144 -> 60 -> 3 -> 3 -> 0. Best: IS -0.18R edge +0.16; OOS -0.18R. Loses after costs everywhere.

### HT2-gdbounce - Gap-down bounce long (gap -2..-5%)  [REJECTED - data artifact]
- TSX funnel: 144 -> 72 -> 47 -> 47 -> 41 -> 11. Best (index gaps up/flat, out at gap fill): IS +0.44R edge +0.64, OOS +0.12R edge +0.32.
- US cold check: every TSX survivor loses money (OOS -0.24..+0.05R; edge -0.01..+0.16, none p<.05). Signal days on TSX have open = day's low 57% of the time in 2000-04 -> bad open prints, not skill.

### HT2-gufade - Gap-up fade short (no-news proxy = no earnings)  [REJECTED - data artifact]
- Funnel: 144 -> 72 -> 35 -> 35 -> 30 -> 0. IS +0.37R edge +0.58 collapses to OOS -0.16R. Same bad-open signature as gdbounce.

### HT2-gucont - Gap-up continuation (gap >= 3%, above 200 SMA; 52-week-high variant)  [REJECTED]
- Funnel: 144 -> 50 -> 7 -> 7 -> 0. Rare on large caps; best IS +0.02R, OOS -0.00R, edge negative OOS. Same verdict as S39.

### HT2-egs - Earnings gap-down short through the 200 SMA  [REJECTED]
- Funnel: 144 -> 60 -> 1 -> 1 -> 0. ~100 trades IS; best IS +0.01R, OOS -0.11R.

### HT3-brk - 3-touch resistance breakout on 1.5x volume, top-25% close (overnight-swing family)  [REJECTED]
- Funnel: 200 -> 40 -> 16 -> 16 -> 0. Best IS +0.18R edge +0.38 (p_rw .37, 175 trades) -> OOS -0.52R. Same verdict as S09/S11.

### HT3-rcl - Support reclaim on volume  [REJECTED]
- Funnel: 200 -> 0. Under 100 trades IS in every config (too rare with a 3-touch support on large caps).

### HT3-vbd - Volume breakdown short below a 3-touch support and the 200 SMA  [REJECTED]
- Funnel: 200 -> 5 -> 0. Negative in every config (best IS -0.13R, OOS -0.21R).
