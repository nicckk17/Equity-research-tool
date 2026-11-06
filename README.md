# AI Equity Research Tool

**Type in a ticker → get a Buy / Hold / Sell call, a target price, upside and downside, and a 150-word rationale, with every number traceable to a scorecard.**

Built by **Nikhil (Nik) Galhotra** · CSC® · CFA Level I candidate (May 2027) · Vancouver, BC · [LinkedIn](https://linkedin.com/in/nikhilgalhotra)

I built this to learn equity analysis by doing it: the method follows what an analyst would do by hand (compare a company to its peers, weigh what matters for its sector, value it on peer multiples), and the tool just does it faster. I can explain every weight and every number without the code.

---

## Example output: Royal Bank of Canada (TSX: RY), 21 Oct 2026

| | |
|---|---|
| **Call** | **HOLD** (weighted score 63%) |
| **Target price** | $259.84 (peer-average forward P/E 14.5x × forward EPS $17.88) |
| **Upside** | −8.4% from $283.62 |
| **Downside case** | −21.2% (repeat of its 5-year max drawdown) → ~$223 |
| **Street check** | Analyst consensus target $302.43 (+6.6%) |

> *Royal Bank of Canada scores 63% against TD, BNS, BMO, CM, NA, which maps to a HOLD. Its strongest area is profitability (100%), led by ROE of 16.2% vs a peer median of 12.8%. The weakest is valuation vs peers (20%), dragged down by P/B of 2.9x vs a peer median of 2.2x…*

Full report: [`equity-research-tool/reports/RY_TO_2026-10-21.html`](equity-research-tool/reports/RY_TO_2026-10-21.html) (download and open in a browser). Sector runs ranking all six big Canadian banks and an apparel group around Aritzia are in [`reports/`](equity-research-tool/reports/).

**What a peer-average model can miss:** RY looks expensive on P/B, but it also has the highest ROE in the group, and a premium P/B usually comes with a premium ROE. That is why the tool's target sits about 15 points below the street's.

---

## How it works

### 6 parameters, 15 metrics, weighted to 100%

| # | Parameter | Metrics | Default | Banks | Energy |
|---|---|---|---|---|---|
| 1 | Valuation vs peers | P/E, EV/EBITDA, P/B | 25% | 25% (no EV/EBITDA) | 25% |
| 2 | Profitability | Net margin, operating margin, ROE | 20% | 20% | 20% |
| 3 | Balance sheet & cash flow | Debt-to-equity, FCF yield | 20% | 20% (CET1 ratio) | **25%** |
| 4 | Growth | 3-yr revenue CAGR, 3-yr EPS CAGR | 15% | 15% | **5%** |
| 5 | Risk | Beta vs TSX, Sharpe, 5-yr max drawdown | 10% | 10% | **15%** |
| 6 | Dividend | Yield, payout ratio | 10% | 10% | 10% |

- **Banks:** EV/EBITDA doesn't work when debt is the raw material, so banks are valued on P/B and ROE, and debt-to-equity is replaced by the CET1 capital ratio.
- **Energy:** commodity swings show up in cash flow, beta and drawdown, so those get more weight; 3-year growth mostly tracks the oil price, so it gets less.

### Scoring and the call
- Each metric: **share of peers beaten** (ties count half). A loss-making company's negative P/E ranks worst, not cheapest.
- Parameter score = average of its metrics; total = weighted sum.
- **≥ 70% Buy · 37.5–70% Hold · < 37.5% Sell** (the 3.8 / 2.5 cut-offs on a 1–5 scale, rescaled).

### Target, upside, downside
- Target = peer-average forward P/E × next year's EPS. Upside = target ÷ price − 1.
- Downside = the stock's 5-year max drawdown, with a check on whether the fall was company-specific or sector-wide.
- Cross-checks against analyst consensus and flags data that looks wrong.

All weights and metric choices live in one file, [`config.json`](equity-research-tool/config.json).

### Run it
```
cd equity-research-tool
pip install -r requirements.txt
python research.py RY                       # one company vs its peers
python research.py --sector canadian_banks  # rank a whole sector
python tests/test_offline.py                # offline self-test, no internet needed
```

---

## Part 2: Strategy backtesting engine (`backtest-engine/`)

The research tool picks *what* to own; this engine tests *when* to own it. It's a Python backtester I built for TSX 60 and top-100 US stocks, tested on years of daily price and earnings data.

What makes the results trustworthy rather than curve-fit:
- Every strategy is compared against **random-entry "twins"** with the same exits and costs, so an edge has to beat luck.
- **In-sample / out-of-sample split** and **rolling walk-forward** (pick settings on 5 years, trade the next 1).
- Corrections for testing many settings: **Romano-Wolf**, **deflated Sharpe ratio**, Harvey-Liu haircut, and a plateau score (good results must hold across neighbouring settings, not one lucky cell).
- Realistic fills, commissions and slippage; results reported as CAGR, Sharpe, Sortino, max drawdown and exposure vs the index.

**Most strategies failed, and the log says why** ([`ta2/docs/REJECTED_LOG.md`](backtest-engine/ta2/docs/REJECTED_LOG.md)).

**Lead result: earnings announcement premium (EAP2)**, based on Frazzini & Lamont (2007): hold a stock from 15 sessions before its earnings date to 2 sessions after.
TSX 2016–2024 (out-of-sample period): **7.0% CAGR, Sharpe 1.28, max drawdown −8%**, positive in 16 of 20 walk-forward windows, still works on US stocks and with double trading costs. Sample report: [`backtest-engine/sample-report/report.html`](backtest-engine/sample-report/report.html).

| Folder | What's in it |
|---|---|
| `ta2/` | Trade simulator, costs, random twins, strategy library, paper-trading bot scaffold for Interactive Brokers |
| `ta3/` | v3: local data store, parameter sweeps, validation suite, HTML reports, quant toolkit (Black-Scholes/Greeks, GARCH, Kelly, Monte Carlo) |
| `tradingview-pine/` | Pine Script versions for charting in TradingView |

Price and earnings data are not included in this repo (licensing and size).

---

## Known limits
- Data comes from free sources (Yahoo Finance, stockanalysis.com); figures should be checked against filings before relying on them.
- Backtest universes are today's index members, so delisted companies are missing (survivorship bias).
- This is a learning and portfolio project, **not investment advice**.

## How I built it
I designed the method, weights and validation rules, and checked the outputs; I used AI coding assistants (Claude and ChatGPT) to write much of the Python. The `--ai` flag can have Claude write the rationale, but by default it's a fixed template so every sentence ties back to a number in the scorecard.
