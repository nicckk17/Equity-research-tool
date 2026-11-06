# ta2 — TSX technical-analysis backtest engine, version 2 (2026-11-03)

v2 of the Phase 2 system (v1 = `phase2/`, 81 scripts, archived). Same rules, same data, same results
(every kept strategy reproduces v1's trades exactly), in ~4,500 lines instead of ~17,000 (v1 phase2 + tsxta), and one command per job.

## Run (from `tsx-ta\`)
First time on a new PC session: `pip install numba pandas numpy scipy` (+ `exchange_calendars` for live).

| Job | Command | Time (PC) |
|---|---|---|
| Is this idea already tested? | `python -m ta2 check inside bar` | 2 s |
| Kept strategies + evidence | `python -m ta2 list` | 1 s |
| Full honest test, TSX | `python -m ta2 test S53` | ~1-3 min (resumes if cut off) |
| US cold check | `python -m ta2 test S53 --universe US` | ~2-4 min |
| One step only | `python -m ta2 test S53 --steps edge` (build, grid, report, named, edge) | |
| One build chunk (3-min limit) | `python -m ta2 test S53 --chunk 0` | |
| Portfolio strategies | `python -m ta2 portfolio S45 --window OOS` / `S43` / `S64 --universe US` | seconds |
| Refresh data | `python -m ta2 data update` / `--universe US` | ~2 min |
| **Trading bot (IB paper)** | `python -m ta2 bot plan` then `python -m ta2 bot run --submit` | ~1 min |
| Bot without a broker | `python -m ta2 bot plan --broker stub` | ~30 s |
| Bot bookkeeping | `python -m ta2 bot sync` / `report` / `close-check` | seconds |
| Older manual scanner | `python -m ta2 live scan` / `fill ...` / `status` (writes an order list only) | seconds |
| Self-checks | `python -m ta2.tests.test_ta2` | ~1 min |

Outputs: `results\ta2\<KEY>[_US][_HO]\` — report_grid.txt (VERDICT + funnel), report_named.txt (named/KEEP versions,
portfolio vs XIU, ladder), report_edge.txt (true edge: skill vs drift R/yr, p, positions needed, % vs index).

## Files
| File | What |
|---|---|
| `config.py` | EVERY rule in one place: windows, fees, slippage, borrow, min risk, twins, bootstrap, sizing, universes |
| `data.py` | Yahoo chart API (no yfinance needed for bars) + earnings, clean loader, close matrix, T-bills |
| `indicators.py` | Wilder indicators = TradingView; per-stock context |
| `engine.py` | ONE trade simulator (all exits: R targets, price targets, indicator/state exits, close-line, ATR trail, breakeven, half-off, time), random twins, costs, bootstrap + Romano-Wolf, portfolio |
| `test.py` | build -> grid -> bootstrap -> report -> named -> true edge |
| `broker.py` | Broker layer: Interactive Brokers (paper only, two guards) + an offline stub for tests |
| `bot.py` | The daily routine: sync -> rule exits -> sized entries with attached stops -> logs. Strategy-agnostic: it asks the strategy module for signals and uses the same exit recipes as engine.py |
| `live.py` | Older S53 scanner, writes an order list for manual entry (v1 logic unchanged) |
| `check.py` | duplicate check against everything ever tested |
| `strategies/` | kept strategies only (+ `_template.py` for new ones, `common.py` exit panel) |
| `docs/REJECTED_LOG.md` | every rejected / untested registry strategy: rule, sources, every dial and variation tested, results, verdict; plus every simulation already run on the kept ones |
| `docs/all_configs_tested.csv.gz` | 79,310 graded configs from v1 (name, n, win, avgR, edge vs random, p, IS + OOS) |
| `docs/METHOD.md` | the testing method and the lessons, in plain English |
| `tests/` | engine fill rules, no look-ahead, v1 parity fingerprints, cheat control |

## The bot (added 2026-11-03)
Broker: **Interactive Brokers paper account** through IB Gateway or TWS (API enabled, Read-Only off).
Ports: Gateway paper 4002 (default), TWS paper 7497. Live ports are refused, and the account id must start
with DU/DF, so the bot cannot trade real money unless someone edits the code on purpose.

Morning routine, after the open (that is when sizing is honest):

    python -m ta2 bot plan            # what it would do, nothing sent
    python -m ta2 bot run --submit    # sends: exits first, then entries with protective stops attached
    python -m ta2 bot report          # R so far, slippage vs the backtest's cost assumption, trades to the 100-trade review

What it does, in order: reads equity/positions/fills from IB and reconciles them with `data\live2\ledger.csv`
(a mismatch stops the run); asks each held position's own exit recipe whether to exit; takes yesterday's
close signals, sizes them on today's actual price, and submits a market order with a stop child attached.
Rails (all in config.py): paper only, 0.33% risk per trade, 20% of equity per position, max 30 open,
max 15 new per day, kill switch at -30% drawdown, stale data refuses to trade, and any position the bot
did not open is reported and never touched (the run stops unless `--allow-foreign`).
Files: `data\live2\` ledger.csv, trades.csv (closed trades with R and slippage), equity.csv, orders_<date>.csv/.md.

## Kept strategies
| Key | Tier | One line |
|---|---|---|
| S53 | strong | MACD 12/26/9 histogram cross-up below zero, opposite-cross exit. Passed everything incl. US + holdout. Live on paper. |
| S55 | strong | 9/21 EMA cross, exit on close below EMA21. Only clean pass of the US cold test. |
| S56 | weak | EMA break + retest (34/8 trail; 50/20 = best diversifier, fails US 2000-15) |
| S31 | weak | RSI divergence + close trigger (bull decades only) |
| S54 | weak | SAR/Force/MACD 2-of-3 votes, flip exit (TSX only) |
| S07X | weak | Slingshot (BB 2.5sd + stoch 30) + 2R (US good, TSX OOS borderline) |
| S14X | weak | W bottom + SMA20 close exit (small, positive everywhere) |
| S45 | protection | Sector ETF rotation: ~index return, < half the drawdown |
| S43 | weak | RS leaders: beats random picks, trails XIU OOS |
| S64 | weak | Skip September on the index ETF |
| HT1 | weak | Humbled Trader parabolic dip: limit buy at prior-day low after a run, index opens up, target run high. Passes TSX + US, but thin after 0.12% fees. |
| S99 | control | Must-pass cheats / must-fail random entries (pipeline check) |

## v1 -> v2 parity (2026-11-03)
Chunk 0 rebuilt for S53, S55, S56, S31, S54, S14X, S99 (and 2 stocks for S07X): every trade identical to v1
(entry bar, exit bar, prices, R, costs). Random twins use a different draw order, so twin averages and p-values
move slightly (e.g., S53 survivor TSX OOS skill +37.3 vs v1 +38 R/yr; US OOS +78 vs +75). Configs sitting right at
p ~ 0.05 can flip between pass/fail (S07X best config: v1 p 0.082, v2 passes; S14X 8 survivors vs v1 11).
S45, S64 reproduce v1 exactly (S45 OOS 9.4%/-16%, S64 TSX IS 7.0%).

## Not ported (on purpose)
v1's ensemble.py (W2_C1 combination) and the one-off S53 research scripts (capacity, monkey, blends, thesis):
their results are recorded in docs/REJECTED_LOG.md and the project notes; rebuild with `engine.portfolio()` if needed.
