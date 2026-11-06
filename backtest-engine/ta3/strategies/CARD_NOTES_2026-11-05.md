# TA3 cards for Claude — 2026-11-05

Six approved cards and seven modules are provided here. ERG has separate S53 and S55 modules; EARN uses SIDE=0 with per-row sides +1/-1, which `W.run_config` and `E.trades` already accept. Nothing needs to be written to tsx-ta to run the supplied smoke script. No strategy tests or backtests were run by Codex: the task explicitly assigns execution and review to Claude. Source/schema and Python syntax were inspected only.

## Running the supplied checks

Run with the project's Python environment and its existing numpy/pandas/numba/parquet dependencies:

```powershell
python -B 'C:\Users\Owner\Desktop\projects for claude\AI Equity research\Chat GPT memory for claude\ta3_cards\test_cards.py' --root 'C:\Users\Owner\Desktop\projects for claude\AI Equity research\tsx-ta'
```

The script imports each delivered module by path, patches strategy lookup in memory, reads existing RY.TO/SU.TO daily files, builds ordinary `W.Prep` windows, then calls **W.run_config** on each module's baseline for each symbol. It requires at least one real trade per module/symbol and finite positive `R`, finite net R, entry, and exit prices. Missing bars, earnings coverage, or no trades fail explicitly; there is no download, generated-price fallback, result writer, or ledger update. Stored daily parquet is preferred; ta2 bars CSV is the fallback. Spent holdout stays excluded.

The causality test recomputes context, raw signals, selected signals, and exit lines after deleting future OHLC bars, including cuts on actual signal dates. It compares all prefix rows and lines. Default coverage includes every OAT configuration on both symbols; `--exhaustive` covers the full combined plan. EARN retains the assumed known session/earnings calendar, not future prices. This is a price-causality check and cannot prove historical calendar publication dates.

The test also validates all six card schemas/statuses, plan counts, required cache knobs, exact ERG pre-gate base signals, yesterday's ER alignment, and EARN's explicit unsupported/missing-calendar errors. It disables bytecode writes and bypasses source-tree loader helpers that call mkdir. No test results are claimed here.

## Knobs

Defaults are in bold. A singleton is intentionally fixed to preserve the base rule or disable the sweep's implicit 0.1 ATR buffer. Boolean and mode knobs necessarily have fewer than three values.

| Module | Knob | Values (default bold) |
|---|---|---|
| BB200 | bb_len | 10, 15, **20**, 30 |
| BB200 | bb_k | 1.5, **2.0**, 2.5 |
| BB200 | trend200 | false, **true** |
| BB200 | buf | 0.1, **0.5**, 1.0 |
| BB200 | exit | time5, **time10**, 2R, trail2atr, middle |
| BB200 | mode | 0, **1** |
| ERG_S53 / ERG_S55 | er_len | 5, **10**, 20 |
| ERG_S53 / ERG_S55 | hi_cut | 0.4, **0.5**, 0.6 |
| ERG_S53 / ERG_S55 | vol_cut | **null/None**, 0.8, 0.9 |
| ERG_S53 / ERG_S55 | chop_k | **0**, 2, 3 |
| ERG_S53 / ERG_S55 | mode | 0, **1** |
| ERG_S53 | buf | **0.5**, fixed |
| ERG_S55 | buf | **0.1**, fixed |
| HI52 | near | 0.02, **0.05**, 0.10 |
| HI52 | trend200 | false, **true** |
| HI52 | stop_atr | **3**, 5, 8 |
| HI52 | exit | trail3, **trail5**, trail8, time63, time126 |
| HI52 | mode / buf | 0, **1** / **0**, fixed |
| ATHD | lookback | 100, 200, **252**, ATH |
| ATHD | k | 3, **5**, 8 |
| ATHD | mode / buf | 0, **1** / **0**, fixed |
| DENS | vote_type | **breakout**, above_mid |
| DENS | v | **2**, 3, 4 |
| DENS | exit | trail3, **trail5**, vote |
| DENS | v_exit | **1**, 2 |
| DENS | mode / buf | 0, **1** / **0**, fixed |
| EARN | L | 1, **2**, 3, 5 |
| EARN | hold | **E**, E+1 |
| EARN | side | **both**, long_only |
| EARN | min_move | **0**, 0.5, 1.0 signal ATR |
| EARN | stop | **2ATR**, fixed; requested none unsupported |
| EARN | mode / buf | 0, **1** / **0**, fixed |

The complete Cartesian upper bound across all seven executable modules is **1,416 configurations**: BB200 720, ERG 162 each, HI52 180, ATHD 24, DENS 72, EARN 96. The actual default plan is smaller because BB200's grid is capped at 600 and OAT/pairs overlap the sampled grid. No inherited S53/S55 knob grids are expanded. The smoke script asserts the actual combined `plan()` count is at most 1,500 using the project's own seed/configuration.

Every knob read by `raw_signals` **or `lines`** is included in SIGNAL_KNOBS, even when its part is stop/exit. This matters because the sweep caches both together. Filter-only thresholds operate on cached columns; `exit_recipe` reads exit knobs anew. ERG fixes base settings and uses the project modules as imported dependencies, so later changes to those source defaults will change the experiment.

## Rule decisions and engine limits

All prices/ATR/anchors use information through signal close t. Mode 0 is signal close; mode 1 is next open. The unchanged engine rejects gaps that leave stop risk nonpositive or below its 0.25-ATR minimum. Costs, slippage, random twins, borrow, and overlap handling are delegated unchanged to the engine.

**Next-open entry-relative stops:** the engine computes `stop = anchor - side * buf * A`. It has no entry-relative initial-stop recipe. Therefore HI52/ATHD/DENS/EARN anchor their initial stop at **signal close minus side × specified ATR distance**, with buf=0. In mode 0 this is exactly entry-relative; mode 1's actual stop distance includes the next-open gap. Using that future open to precompute the anchor would violate the task's signal-time constraint. Exact next-open entry-minus-k-ATR stops need engine support; these modules do not pretend to implement that feature.

**Trailing convention:** `trail_atr` uses frozen signal-bar ATR and favorable intrabar high/low since entry, ratchets only after each bar, and applies on the next bar. It is not a rolling-current-ATR trail. Mode 0 does not inspect the already-completed entry bar for stop/trail fills. The engine counts max_hold from its first simulated bar: mode 1's 252-bar cap closes at entry+251, while mode 0 closes at entry+252. These are existing engine conventions.

**BB200:** the supplied card's knob table and prose disagree: prose mentions middle-band reversion, while its four exit knob values omit that rule. Original defaults and all four options are preserved, with `middle` added as a fifth selectable exit. They are alternative recipes, not a middle-band overlay on every recipe. Recent swing low means the rolling 10-bar low inclusive of t, a causal unconfirmed swing proxy, matching S53's convention. Every below-band bar is a candidate (EPISODE_GAP=1); engine nonoverlap controls repeated entries. Population standard deviation matches ta2 Bollinger. The `middle` recipe uses `close_line="above_middle"` with line `2*close - middle`; the engine's `close < line` condition then expresses `close > middle`. Its max_hold=60 is a safety cap. **Engine limitation:** close_line ignores the entry bar (`j > e`), so with next-open entry, a same-entry-day middle-band recovery will not exit that day. An exact recovery exit on that bar requires engine support. `time5`, `time10`, `2R`, and `trail2atr` use EXIT_PANEL unchanged.

**ERG:** er_len is n differences, denominator sum(abs(diff(close)), n); numerator abs(close-close.shift(n)). A fully observed flat window has ER=0. The entry gate uses **yesterday's ER and yesterday's volatility percentile**. Equality at hi_cut/vol_cut passes. RV20 is 20 daily simple returns' population standard deviation. Its percentile is the current rank (average rank for ties) in a trailing 252-RV-observation window, then lagged one bar. This is a historical distribution, never a full-sample rank. lo_cut is fixed at 0.2 because no grid was supplied; chop_k requires the k consecutive days ending yesterday below that threshold. Missing ER fails closed; missing volatility only blocks when that gate is enabled. Base episode detection/filtering occurs before ERG, so rejected episodes still consume the base spacing. S53 defaults: 12/26/9, zero=true, weekly=false, buf=.5, opposite_cross, max_hold60. S55 defaults: 9/21, gap20, anchor10, clear/slope/breakout=false, buf=.1, EMA21 exit, max_hold60. Default mode1 preserves the base entry; mode0 is an explicit variation. Claude will compare each ERG variant against **random-skip twins with the same skip percentage**; the normal engine random-entry twins alone do not supply this additional control.

**HI52:** the 252-bar high includes t, with a full window required. A candidate must have no qualifying nearness bar in the preceding 20 bars; continuous proximity never retriggers every 20 days. Trend filtering occurs after this episode rule. stop_atr is independently varied from trail distance. `time63`/`time126` use time_bars=63/126 and max_hold=253 to avoid truncating the requested entry-relative time stop.

**ATHD:** the breakout threshold always excludes t. ATH is an expanding highest high of **available** history, requiring 252 prior observations; it cannot assert a true lifetime high before local data starts. Every new breakout bar is a candidate; no target, k governs both initial stop and trail, max_hold252.

**DENS:** all 20/55/100/200 prior channels must be ready. Midpoints use prior rolling high/low, not future/current extremes. Entry requires a genuine vote crossing from below v, so the first fully warmed bar is not automatically treated as a crossing. Initial stop is fixed at 3 signal ATR, independent of exit choice. `vote` recipe is a state exit at the next open after vote < v_exit; equality does not exit. v_exit=2 with v=2 is valid. Both vote and trailing recipes have a 252 simulated-bar safety cap.

## EARN: integration, timing, and unsupported no-stop branch

`ta2.data.fetch_earnings` gets yfinance earnings timestamps, removes timezone and normalizes to the calendar date before saving. `D.earnings` normalizes, sorts, and deduplicates those saved dates. No before-open/after-close indicator or historical schedule-announcement timestamp survives. `context(df, earn_dates)` maps dates to `df.index.searchsorted` positions; standard **W.Prep calls context(df) without dates**, so EARN cannot work from ordinary Prep alone. Rather than silently return no trades, EARN raises when its explicit calendar context is absent.

For a prepared EARN run, load the delivered module by path (as the test does), construct W.Prep with its strategy lookup pointing to that module, then call `earn.prepare_earnings(prep)` **before** `W.run_config` or worker dispatch. The helper calls D.earnings for each symbol using the selected universe, attaches schedule dates, and clears only the in-memory cache. `W.sweep` constructs and dispatches its own Prep without a hook, so its existing one-call CLI is **not ready for EARN** without Claude supplying that preparation step in a caller. No source changes or global monkeypatch are installed by these files. The smoke test supplies the same enrichment from read-only CSV access.

E is the first trading session on/after the saved report calendar date. Direction uses `close[t] - close[t-L]` with t=E-1; flat moves are skipped, and minimum-move comparison is inclusive. Mode0 enters that close; mode1 enters E open. E and E+1 exits use max_hold=1 and 2, respectively, since both modes start simulation on E. This expresses the requested calendar-session exits exactly, subject to the stop and available end-of-data; no exit uses knowledge of the reported result. Both directions are carried in one signal table and share one stock-level open-position limit.

Reports made after E close often react on E+1. We **do not** shift event dates using the later observed reaction or inferred report timing: E stays the recorded date, and hold=E+1 is a declared variant. This avoids outcome-based event alignment. Nevertheless, historical dates may be revised and the store does not establish that each event was known at E-1. These are **conditional-calendar experiments, not proven point-in-time investable backtests**. Strict no-look-ahead for calendar availability needs a point-in-time pre-announced calendar not present here.

`attach_earnings` maps report dates using a session calendar, then stores the scheduled E-1 timestamps. For truncated-price tests the original date-only session calendar is retained as assumed exogenous scheduling information, so deleting E's OHLC cannot erase the preceding signal. Dates outside calendar coverage are ignored. Real production use should supply an exchange session calendar, especially for suspended/missing-symbol bars; the supplied default uses observed session dates to match context's existing mapping.

**Requested stop=none is not supported by the unchanged engine.** Every trade requires a finite stop and positive risk, and R/cost sizing/random twins all divide by that risk. EXIT_PANEL has no way to disable stop execution while retaining a separate risk unit. A distant fake stop would change the strategy and its R units. Consequently the card records `requested_unsupported.stop=["none"]`, the executable stop grid contains only 2ATR (baseline), and a manually supplied stop="none" raises NotImplementedError. A real no-stop branch requires explicit engine support for independent risk normalization and disabled stop checks, to be reviewed separately by Claude.

## Recipes beyond EXIT_PANEL

No engine modifications are included. These module-local dictionaries use already supported engine keys:

| Module | Recipe |
|---|---|
| BB200 middle | close_line="above_middle", max_hold=60 (entry-day limit above) |
| ERG_S53 | Base state="hist", max_hold=60 |
| ERG_S55 | Base state="ema", max_hold=60 |
| HI52 trail | trail_atr=3/5/8, max_hold=252 |
| HI52 time | time_bars=63/126, max_hold=253 |
| ATHD | trail_atr=k, max_hold=252 |
| DENS trail | trail_atr=3/5, max_hold=252 |
| DENS vote | state="vote", max_hold=252 |
| EARN | max_hold=1/2, no target, mandatory 2ATR initial stop |

No duplicate search, web research, performance claim verification, backtest execution, or random-skip comparison was performed. Source attributions for the five new cards are those supplied in the approved task, not verified quotations or reproductions of the cited papers.
