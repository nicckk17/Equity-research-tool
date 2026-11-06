# ta3 strategy ports — 2026-11-05

All deliverables are staged here. Nothing in `tsx-ta` was edited. Imports use
`ta3.knobs` and existing ta2 shared helpers so these modules work both here and
when Claude installs them into `ta3/strategies`.

## Review and parity

From `AI Equity research/tsx-ta`, with the existing project environment and
`PYTHONPATH=.`:

```text
python -m pytest "../Chat GPT memory for claude/ta3_ports/test_ports.py"
```

The four tests load these staged files without copying them into the package.
Each checks RY.TO and SU.TO, TSX daily, IS and OOS. They compare the default LIVE
survivor's signal table, trade count, ordered entry/exit dates, fills, reason,
risk, and individual net R at `C.COST_MAIN`. They also cover every additional
KEEP recipe in S55, S56, and S07X through explicit knob overrides. Random twins
are not compared because their seeds differ; the actual trades do not depend
on those seeds. Store/CSV OHLCV equality is asserted first so data drift cannot
be mistaken for a strategy mismatch. The ta3 daily store must already exist.

Only static syntax/interface/cache-dependency checks were performed here.
Parity tests and runtime validation are left to Claude as requested.

## Shared conventions

Defaults use each source's `KEEP[LIVE]`, not its older `NAMED` or `LADDER` base.
All strategies are long only. Numerical sweeps have 3–6 values; Boolean gates
and S55/S56/S07X entry modes have only their two meaningful states, matching the
S53 template. Numerical guard constants, side signs, fraction-of-position
semantics (half means half), and engine-wide ATR(14), costs, fills, and risk
rules remain shared definitions rather than strategy knobs.

`part` identifies what a knob changes. `SIGNAL_KNOBS` additionally includes
any stop/filter/entry/exit knob used to build raw rows or indicator lines,
because `sweep.run_config` caches BOTH by that tuple. This is necessary for
correct OAT/pair/grid results. Exit-rule-specific knobs are intentionally
inactive under other rules. Grids may also contain equivalent configs when a
gate is off. The unchanged sweep planner materializes the entire Cartesian
product before sampling, so run baseline/OAT/pairs first; a full grid over these
many knobs requires a separately reviewed planner change or a reduced knob set.

No weekly projection was introduced. All indicators use trailing/current-close
history. The only higher-timeframe feature is S56's previous calendar month:
its levels use exactly month M-1, never any part of month M. HT1 is daily only
because its existing index-bar helper aligns daily index opens.

## S55

Default: 9/21 EMA cross, long, no extra gate, next open, 0.1 ATR below
10-bar low, close-break of EMA21 with next-open exit, max 60 bars.
The second KEEP recipe is `exit_ema=9, buf=0.5`.

The tuple-valued `lengths` knob retains the original pair/stack choices and
adds nearby fast-pair values. A three-length tuple requires all EMAs to slope
with the stack, exactly as ta2. Both long AND short raw transitions consume
the 20-bar debounce before long-only selection. Pair equality retains the
last direction; a mixed stack resets it; initial history is not a cross.
Invalid OHLC bars are removed for signals, but exit lines use original df,
as in ta2. `exit="ema"` plus `exit_ema` generalizes ta2's ema9/ema21/ema50 names.
Range/efficiency defaults preserve the source's dormant gate definitions;
neighbor values test faster/slower windows and looser/tighter gates.

| Knob | Default | Values | Part | Why / quantity varied |
|---|---|---|---|---|
| `lengths` | `(9, 21)` | `[(7, 18), (9, 21), (12, 26), (20, 50), (50, 200), (9, 21, 55)]` | signal | EMA pair or rising stack. |
| `gap` | `20` | `[10, 15, 20, 25, 30]` | signal | minimum bars between raw episodes. |
| `anchor_bars` | `10` | `[5, 8, 10, 15, 20]` | stop | trailing low stop anchor. |
| `eff_bars` | `20` | `[10, 15, 20, 25, 30]` | filter | efficiency lookback. |
| `eff_min` | `0.25` | `[0.15, 0.2, 0.25, 0.3, 0.35]` | filter | minimum efficiency. |
| `clear` | `False` | `[False, True]` | filter | require efficiency gate. |
| `slope` | `False` | `[False, True]` | filter | require all EMAs rising. |
| `breakout` | `False` | `[False, True]` | filter | require range breakout. |
| `range_bars` | `20` | `[10, 15, 20, 25, 30]` | filter | prior range lookback. |
| `buf` | `0.1` | `[0.05, 0.1, 0.3, 0.5]` | stop | stop buffer in ATR. |
| `exit` | `'ema'` | `['ema', 'reverse_cross', '2R', 'trail3atr']` | exit | exit rule. |
| `exit_ema` | `21` | `[9, 13, 21, 34, 50]` | exit | EMA close-break period. |
| `target_R` | `2.0` | `[1.5, 2.0, 2.5, 3.0]` | exit | fixed profit target in R. |
| `trail_atr` | `3.0` | `[2.0, 2.5, 3.0, 3.5]` | exit | chandelier ATR multiple. |
| `max_hold` | `60` | `[40, 50, 60, 80]` | exit | hard holding limit. |
| `mode` | `1` | `[0, 1]` | entry | signal close or next open. |

## S56

Default: EMA34/8, first directional retest within 2%, strong body >=60%,
next open, 0.5 ATR below signal low, EMA8 close-break exit, max 120 bars.
The diversifier KEEP recipe uses `main=50, trail=20, tol=0.01, strong=False,
exit="ema_main"`.

`raw_tol` and `tol` are deliberately separate. ta2 consumes the first
*directional* 2%-zone retest before the optional narrower tolerance, strong
body, slope, and ATR gates. Moving the tolerance gate into setup detection
would change trades. `tol > raw_tol` cannot widen the raw channel; widen
`raw_tol` too if desired. Equality keeps the cross direction and deep wick
overshoots still count as touches. The monthly pivot default is the original
Fibonacci R3/S3 formula P +/- previous-month range; `pivot_span` varies that
range multiple. Main/trail values include the second kept pair and nearby
periods; the remaining ranges test sensitivity around source thresholds.

| Knob | Default | Values | Part | Why / quantity varied |
|---|---|---|---|---|
| `main` | `34` | `[21, 28, 34, 50, 55]` | signal | cross/retest EMA. |
| `trail` | `8` | `[5, 8, 10, 13, 20]` | exit | exit EMA. |
| `retest_bars` | `20` | `[10, 15, 20, 25, 30]` | signal | cross setup expiry. |
| `raw_tol` | `0.02` | `[0.01, 0.015, 0.02, 0.025, 0.03]` | signal | raw retest zone before gates. |
| `gap` | `10` | `[5, 8, 10, 15, 20]` | signal | raw episode gap. |
| `tol` | `0.02` | `[0.005, 0.01, 0.015, 0.02, 0.025]` | filter | optional tighter retest tolerance. |
| `strong` | `True` | `[False, True]` | filter | require strong candle. |
| `body_min` | `0.6` | `[0.4, 0.5, 0.6, 0.7, 0.8]` | filter | minimum body / range. |
| `slope` | `False` | `[False, True]` | filter | require favorable main EMA slope. |
| `buf` | `0.5` | `[0.1, 0.3, 0.5, 0.8, 1.0]` | stop | stop buffer in ATR. |
| `exit` | `'ema_trail'` | `['ema_trail', 'ema_main', 'pivot', '2R']` | exit | exit rule. |
| `target_R` | `2.0` | `[1.5, 2.0, 2.5, 3.0]` | exit | fixed profit target in R. |
| `pivot_span` | `1.0` | `[0.618, 0.786, 1.0, 1.272]` | exit | previous-month pivot range multiple. |
| `max_hold` | `120` | `[60, 90, 120, 150]` | exit | hard holding limit. |
| `mode` | `1` | `[0, 1]` | entry | signal close or next open. |

## S07X

Default: long `confirm`, BB 2.5 SD, stochastic <30, independently debounced
2-of-3 (band/oversold/support), entry at confirmation-bar close (`mode=0`),
0.1 ATR below setup low, 2R target, max 60 bars. The second KEEP recipe is
`exit="half1R_trail2atr"`, with all other defaults unchanged.

Ambiguity preserved: the source calls this a next-day buy stop above the
setup high, but its actual survivor confirms `high[t] > high[t-1]` and enters
at t's CLOSE. This port preserves that rule. It does not simulate an intraday
buy-stop fill. ATR comes from confirmation bar t; anchor comes from setup
bar t-1. All raw qualifying bars reset the five-bar suppression window,
including invalid-ATR qualifications; eligibility requires ATR at both bars.

Only the kept confirmation family is retained. Short, close, cross20, and
swing-anchor families and their unused trend/earnings flags are omitted.
`required` can select the original independent 2-vote, 3-vote, or
3-vote-plus-candle channel; this changes episode generation, not just a late
filter. Candle knobs are inactive for the default 2-vote channel.

All four original causal support channels remain: tested SMA, horizontal
pivots, double bottom, and Fibonacci. Pivots become known only after
`strength` right-hand bars. The most recently confirmed high replaces the
Fib leg and simultaneous lows are processed after high/low pairing, exactly
as ta2. `ma_tol` preserves the source's shared 0.5-ATR tolerance across MA,
horizontal, and Fib support. BB middle/SD reconstruction and default context
arrays preserve the original arithmetic. The unused swing calculation was
removed. Feature JIT uses `cache=False` so it writes no compiled cache here.
Neighbor values vary the original proximity, spacing, count, age, and candle
cutoffs without substituting different support definitions.

| Knob | Default | Values | Part | Why / quantity varied |
|---|---|---|---|---|
| `bb_bars` | `20` | `[15, 18, 20, 22, 25]` | signal | Bollinger lookback. |
| `bb_sd` | `2.5` | `[2.0, 2.25, 2.5, 2.75, 3.0]` | signal | lower band SD multiple. |
| `stoch_bars` | `14` | `[10, 12, 14, 16, 20]` | signal | stochastic lookback. |
| `stoch_smooth` | `3` | `[1, 2, 3, 4, 5]` | signal | stochastic smoothing. |
| `stoch_max` | `30` | `[10, 20, 25, 30, 35]` | signal | oversold threshold. |
| `required` | `'2'` | `['2', '3', '3+candle']` | signal | votes required; independently debounced. |
| `gap` | `5` | `[3, 4, 5, 7, 10]` | signal | preceding raw qualification suppression window. |
| `support_ma` | `50` | `[34, 40, 50, 60, 75]` | signal | support SMA period. |
| `strength` | `5` | `[3, 4, 5, 6, 7]` | signal | pivot confirmation strength. |
| `pivot_bars` | `252` | `[126, 189, 252, 315]` | signal | confirmed low retention. |
| `ma_tol` | `0.5` | `[0.25, 0.4, 0.5, 0.75, 1.0]` | signal | support proximity in ATR. |
| `ma_look` | `50` | `[30, 40, 50, 60, 75]` | signal | prior MA touch episode window. |
| `ma_count` | `2` | `[1, 2, 3, 4]` | signal | minimum prior MA touch episodes. |
| `horizontal_gap` | `10` | `[5, 8, 10, 15, 20]` | signal | minimum horizontal pivot spacing. |
| `horizontal_count_min` | `3` | `[2, 3, 4, 5]` | signal | minimum horizontal support pivots. |
| `double_gap` | `10` | `[5, 8, 10, 15, 20]` | signal | minimum double-bottom spacing. |
| `double_age` | `120` | `[60, 90, 120, 150, 180]` | signal | maximum double-bottom age. |
| `double_tol` | `0.02` | `[0.01, 0.015, 0.02, 0.025, 0.03]` | signal | double-bottom relative tolerance. |
| `fib_impulse` | `0.05` | `[0.03, 0.04, 0.05, 0.075, 0.1]` | signal | minimum Fibonacci impulse. |
| `fib_age` | `252` | `[126, 189, 252, 315]` | signal | Fibonacci leg expiry. |
| `fib_a` | `0.5` | `[0.382, 0.45, 0.5, 0.55]` | signal | first Fibonacci retracement. |
| `fib_b` | `0.618` | `[0.55, 0.6, 0.618, 0.65, 0.7]` | signal | second Fibonacci retracement. |
| `pin_ratio` | `2.0` | `[1.5, 2.0, 2.5, 3.0]` | signal | pin wick/body ratio. |
| `top_fraction` | `0.3333333333333333` | `[0.25, 0.3333333333333333, 0.4, 0.5]` | signal | maximum close distance from high / range. |
| `body_min` | `0.6` | `[0.4, 0.5, 0.6, 0.7, 0.8]` | signal | full candle body/range minimum. |
| `buf` | `0.1` | `[0.05, 0.1, 0.3, 0.5]` | stop | setup-low stop buffer in ATR. |
| `exit` | `'2R'` | `['2R', 'half1R_trail2atr', 'trail2atr', 'time10']` | exit | exit rule; includes both kept variants. |
| `target_R` | `2.0` | `[1.5, 2.0, 2.5, 3.0]` | exit | fixed profit target in R. |
| `half_R` | `1.0` | `[0.5, 1.0, 1.5, 2.0]` | exit | half position profit level in R. |
| `trail_atr` | `2.0` | `[1.5, 2.0, 2.5, 3.0]` | exit | chandelier ATR multiple. |
| `time_bars` | `10` | `[5, 8, 10, 15, 20]` | exit | timed exit bars. |
| `max_hold` | `60` | `[40, 50, 60, 80]` | exit | hard holding limit. |
| `mode` | `0` | `[0, 1]` | entry | signal close or next open. |

## HT1

Default: long parabolic family only, >=5 of last 6 close changes up OR
>=15% over 10 bars; limit at prior-day low, index opens flat/up, same-bar
order mode 3, buffer 1.0 prior-bar ATR, target highest high of prior 6 bars,
max 5 bars. Rejected fgd/day2/frd/bag families are omitted.

Prior setup/ATR/target are known before t. Only current open and index open
are used for pricing/filtering; current low is used solely to confirm the
resting limit filled. Price and stop anchor are both min(current open,
prior low), preserving the source's opening-gap improvement. No episode
suppression is added. `warmup=201` preserves the source's fixed starting bar
even when trend filtering is off. Alternative `limit_lag` values change the
resting level only, not the setup's as-of bar or ATR. An impossible up-count
(e.g. 6 required within 4 changes) simply leaves the return arm available,
matching the OR rule.

The existing `index_bars` helper chooses XIU.TO for TSX and SPY for US,
uses an exact-date join without backfilling, and returns missing values if
index data are absent. Missing index data fail the default gate. The helper's
module-level cache is retained; data changes require a fresh process/cache.
The helper is not suitable for intraday index alignment, hence daily-only.
Alternate entry modes 0/1 are close/next-open experiments on the same filled
order signals; mode 3 is the survivor. `max_hold` is now explicit across all
exit choices (the default opp recipe matches ta2 exactly); change it for
longer 2R experiments. Neighbor ranges vary run strength, window lengths,
stop width, target window, and holding time around the kept recipe.

| Knob | Default | Values | Part | Why / quantity varied |
|---|---|---|---|---|
| `limit_lag` | `1` | `[1, 2, 3]` | entry | bars back for limit-price low. |
| `up_bars` | `6` | `[4, 5, 6, 7, 8]` | signal | up-close count window. |
| `up_min` | `5` | `[3, 4, 5, 6]` | signal | minimum up closes. |
| `run_bars` | `10` | `[5, 8, 10, 12, 15]` | signal | alternative run lookback. |
| `run_min` | `0.15` | `[0.1, 0.125, 0.15, 0.175, 0.2]` | signal | alternative minimum run return. |
| `target_bars` | `6` | `[3, 5, 6, 8, 10]` | exit | prior run-high lookback. |
| `warmup` | `201` | `[151, 181, 201, 221, 251]` | signal | first eligible signal bar. |
| `trend_bars` | `200` | `[150, 175, 200, 225, 250]` | filter | optional trend SMA. |
| `idx_up` | `True` | `[False, True]` | filter | index opens flat/up. |
| `trend` | `False` | `[False, True]` | filter | prior close above trend SMA. |
| `streak` | `False` | `[False, True]` | filter | require up-close count arm. |
| `big` | `False` | `[False, True]` | filter | require return arm. |
| `buf` | `1.0` | `[0.5, 0.75, 1.0, 1.25, 1.5]` | stop | order-price stop buffer in prior ATR. |
| `exit` | `'opp'` | `['opp', 'day', 'next', 'time3', '2R']` | exit | exit rule. |
| `max_hold` | `5` | `[3, 5, 7, 10]` | exit | hard holding limit. |
| `next_bars` | `1` | `[1, 2, 3]` | exit | short hold exit bars. |
| `time_bars` | `3` | `[2, 3, 4, 5]` | exit | timed exit bars. |
| `target_R` | `2.0` | `[1.5, 2.0, 2.5, 3.0]` | exit | fixed profit target in R. |
| `mode` | `3` | `[0, 1, 3]` | entry | close, next open, or original limit fill. |

