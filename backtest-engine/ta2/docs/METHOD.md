# How ta2 tests a strategy (and what v1 taught us)

## The question every test answers
"Does this rule pick better entry moments than random, after costs, on data it was not tuned on?"
Not "does it make money": in a rising market almost any long rule makes money (drift + survivorship).

## Data
- TSX 60 (today's members) daily bars from Yahoo, 1995 on; US top-100 (by 2026 market cap, history to 2000) for the cold check.
- Survivorship bias: delisted losers are missing, which flatters long strategies. That is why every trade is compared with random twins.
- OHLC split-adjusted, not dividend-adjusted (patterns use traded prices); benchmarks use dividend-adjusted closes.

## Windows
- IS 2000-2015: the only place to choose settings.
- OOS 2016-Oct 2024: confirm, never tune.
- Holdout Nov 2024-Oct 2026: SPENT (opened once for every v1 family). Report only.
- US cold check: same settings, a market never looked at while choosing.
- Forward (Nov 2026 on): the only untouched data left -> paper trading.

## Trade rules
Entry at the signal close or the next open (a dial). Stop = anchor -/+ buffer x ATR (a dial); skip if risk < 0.25 ATR.
Per bar: gap through stop -> open; rule exit -> next open; stop touched -> stop; gap through target -> open; target -> target;
same bar stop + target = stop. Costs 0.12%/side (0.05% sensitivity), +0.10% on stop fills, 0.5%/yr borrow on shorts.
One position per stock at a time. R = entry-to-stop risk; results in R after costs.

## The random twins (the key idea)
Each trade gets 5 twins: same stock, side, window, stop width in ATR, same exit, random entry day.
Edge = trade R - twin R. Drift R/yr = what random entries earned; skill R/yr = the edge per year.

## Luck control
Week-block bootstrap (2,000 draws, trades of the same week stay together, same draw for every config) gives a
p-value per config and a Romano-Wolf max-t p across ALL configs of the strategy (corrects for trying many).
Funnel: >=100 IS trades -> avgR > 0 -> beats random -> Romano-Wolf p < 0.05 (IS) -> OOS: >=50 trades, avgR > 0,
beats random, p < 0.05 -> US cold -> forward.
Calibration: S99 control (cheats must pass, random must fail) - it does.

## Reading the results
- Always read skill R/yr WITH its p (a random strategy showed +23 R/yr skill at p 0.24).
- avgR alone is meaningless (drift). Win rate alone is meaningless (S78: 69% wins, 0R).
- "% vs index over the same days" tells you if it beats simply holding XIU while in the trade. For every v1 strategy: about equal.
- Portfolio results depend on construction: S53 needs ~18-26 positions open on average (55 at peak) to take every signal.

## Lessons (v1, 86 strategies, ~79,000 configs)
1. Shorts lost everywhere on large caps.
2. Most rules = drift. Only S53 cleared every hurdle; S55 is the only clean US pass; several weak timing edges.
3. Fixed stop/target exits waste timing edges; signal-based or trailing exits keep them.
4. Regime/trend/momentum/sector filters flip between 2000-15 and 2016-26.
5. No signal-day feature predicts which S53 trade becomes a big winner: take every signal, small size.
6. No rule beat buy-and-hold in money; the honest pitch is "timing skill vs random" and "smaller crashes".
7. Pre-declare the pass rule BEFORE running; one tweak family at a time; pick on IS only.
