# ta3 — backtest engine v3 (2026-11-04)

Built on top of ta2: the same trade simulator, fills, costs, slippage, random-entry twins, windows and
sizing (ta2/engine.py + ta2/config.py are imported, not copied), so every number stays comparable with
v1/v2. Parity check: the S53 default config reproduces ta2's S53 survivor trades exactly.

What v3 adds:

| Piece | File | What it does |
|---|---|---|
| Local data store | `store.py` | Parquet per symbol + DuckDB catalogue (`data/store/`), every timeframe from one base (D/W/M from daily; 5m/15m/1h/4h from stored intraday), data-quality score, bad-open years flagged, intraday downloads (Yahoo free, Alpaca US with your keys) that keep growing the archive |
| Knobs | `knobs.py` | every moving part of a strategy declared once with its default and values to try |
| Sweep | `sweep.py` | baseline, one knob at a time, every pair of knobs, full grid (sampled to 600), per timeframe, multiprocessing, Romano-Wolf luck correction across every config |
| Validation | `validate.py` | knob impact, plateau score, deflated Sharpe with the global trial count (v1's 79,310 + every ta3 sweep), Harvey-Liu haircut, year by year, Monte Carlo drawdown, **rolling walk-forward** (pick on 5 yrs, trade next 1), real % portfolio vs index |
| Graph report | `report.py` | one fixed-template HTML page per strategy x universe (12 sections) |
| Quant | `quant.py` | Black-Scholes + Greeks + implied vol, Monte Carlo trades/paths, risk of ruin, Kelly, position size, vol targeting, GARCH(1,1), Hurst, Sharpe/Sortino/drawdown/CAGR, correlation between systems |
| Order flow | `orderflow.py` | session/anchored VWAP + bands, relative volume, volume profile (POC/VAH/VAL); from ticks: Lee-Ready side, footprint, delta/CVD, stacked imbalances, absorption, big prints |
| Research loop | `research.py` | rule cards from your scraping skills -> duplicate check -> your approval -> strategy file -> test -> log |

## Commands (from `tsx-ta\`)
First time: `pip install numba pandas numpy scipy duckdb pyarrow plotly`

| Job | Command |
|---|---|
| Build the local store from ta2's CSVs | `python -m ta3 data import` and `--universe US` |
| Download intraday bars (PC) | `python -m ta3 data intraday --interval 60m` ; US minute: `--universe US --source alpaca --interval 1Min` |
| Data quality | `python -m ta3 data quality` |
| Full pipeline + report | `python -m ta3 run S53 --tf D,W,1h` -> `results\ta3\S53_TSX\report.html` |
| Quick look (no grid) | `python -m ta3 run S53 --parts oat,pairs` |
| Research queue | `python -m ta3 research list` / `new card.json` / `approve KEY` / `code KEY` / `log KEY --verdict weak` |
| Self-checks | `python -m ta3.tests.test_ta3` |

## Adding a strategy
Write a rule card (see `python -m ta3 research example`), `research new`, `approve`, `code` -> fill
`raw_signals()` (rows: t, side, anchor, A, opp + one bool column per filter knob; data up to bar t only).
`SIGNAL_KNOBS` = knobs that change the raw signal list (cached on those). Exits come from the ta2 exit panel
(`2R`, `trail3atr`, `time10`, ...) or a state line returned by `lines()`.

## Reading a report
1. Verdict: baseline edge vs random with p_rw < 0.05 in IS **and** OOS, plateau >= 0.5, walk-forward OOS edge > 0
   with p < 0.05, deflated Sharpe > 0.95 for a strong claim.
2. Knob impact tells you which moving part drives the result; a big swing on a knob = fragile there.
3. Heatmaps: trust broad warm areas, not single hot cells.
4. Timeframes: an edge that holds on several timeframes is more believable than one that only works on one.

## Known limits
- Survivorship: universes are today's TSX 60 / top-100 US; delisted names need a paid data source.
- Intraday history: Yahoo 60m ~2 years, so intraday windows are 60/40 by share of sample.
- Order flow from ticks needs tick data (not stored yet); bar-based tools work now.
- Pre-2005 TSX opens are bad prints: the report shows `badopen_share`; judge next-open entries on US or 2005+.
