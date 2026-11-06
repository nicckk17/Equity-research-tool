# AI Equity Research Tool

Type in a company name or ticker, or a whole sector. The tool pulls the numbers, scores each company against its peers on six weighted parameters, ranks the sector to find the best name, and returns:

1. **Recommendation**: Buy / Hold / Sell
2. **Target price**
3. **Upside %** and **Downside %**
4. **Rationale**: up to 150 words

You get a one-screen summary in the terminal and a full HTML report (opens in your browser) that shows every number behind the call.

---

## Setup (once)

1. Install Python 3.10+ from python.org. On the first installer screen, tick **"Add Python to PATH"**.
2. Double-click **`setup.bat`**. It installs the libraries and runs the offline tests. Every line should say `ok`.

## Run it

- Double-click **`run.bat`** and type a ticker or name, **or**
- From a terminal in this folder:

```
python research.py --sector canadian_banks        <- find the best in the sector
python research.py --sector integrated_energy
python research.py RY                             <- one company vs its peers
python research.py "Suncor Energy"
python research.py CVE --peers SU.TO,CNQ.TO,IMO.TO
python research.py --data data/canadian_banks_2026-10-16.json   <- run from saved web data
python research.py TD --ai
```

**Sector mode** scores every company in the group against all the others, ranks them #1 to last, and writes a ranking page (`reports/<sector>_<date>/index.html`) with a full report for each company. Groups are listed in `peers.json`.

**`--data`** runs from a data file collected from the web (stockanalysis.com ratios, financials and monthly prices) instead of Yahoo Finance. That's how the cloud run worked.

Tickers without a suffix are assumed to be TSX (`RY` → `RY.TO`). Reports are saved to `reports/` as `TICKER_DATE.html` and `.json`.

`--ai` has Claude write the rationale from the scorecard. It needs `pip install anthropic` and an `ANTHROPIC_API_KEY` environment variable. Without it, the tool fills in a fixed template from the scorecard, so every number in the rationale traces back to a row in the report.

---

## Method (what you need to explain without the AI)

### Parameters and weights

| # | Parameter | Metrics used | Default | Banks | Energy |
|---|---|---|---|---|---|
| 1 | Valuation vs peers | P/E, EV/EBITDA, P/B (lower = better) | 25% | 25% (no EV/EBITDA) | 25% |
| 2 | Profitability | Net margin, operating margin, ROE | 20% | 20% (ROE, net margin) | 20% |
| 3 | Balance sheet & cash flow | Debt-to-equity (lower), FCF yield | 20% | 20% (**CET1 ratio**) | **25%** |
| 4 | Growth | 3-yr revenue CAGR, 3-yr EPS CAGR | 15% | 15% | **5%** |
| 5 | Risk | Beta vs TSX (lower), Sharpe, 5-yr max drawdown | 10% | 10% | **15%** |
| 6 | Dividend | Yield, payout ratio (lower) | 10% | 10% | 10% |

**Why banks are different:** EV/EBITDA doesn't work for banks because debt is their raw material (deposits and borrowings), not just financing. They're valued on P/B and ROE. Debt-to-equity is replaced by CET1, the regulatory capital cushion that OSFI watches.

**Why energy is different:** commodity price swings show up in cash flow, beta and drawdown, so those get more weight. Growth gets less, because 3-year growth mostly tracks the oil price rather than the company.

### Scoring each metric (0–100%)

> **score = peers beaten ÷ peers compared**, with a tie counting as half

Beat all 5 peers → 100%. Beat none → 0%. Beat 3 of 5 → 60%. A negative P/E or EV/EBITDA (i.e., the company is losing money) ranks as the worst, not the cheapest.

**Parameter score** = average of its metric scores. **Weighted score** = Σ (weight × parameter score).

### The call

| Weighted score | Call |
|---|---|
| 70% or higher | **Buy** |
| 37.5% to 70% | **Hold** |
| below 37.5% | **Sell** |

These are the original 3.8 and 2.5 (on a 1–5 scale) converted: (3.8 − 1) ÷ 4 = 70%, (2.5 − 1) ÷ 4 = 37.5%.

### Target price, upside, downside

- **Target price** = average forward P/E of the peers × company's forward EPS (analyst consensus for next year). Peer P/Es below 3x or above 60x are dropped as outliers.
- **Upside %** = target ÷ current price − 1
- **Downside %** = the stock's worst peak-to-trough fall over 5 years (max drawdown). The report also shows the price that fall would imply from today.
- For every stock, the report also shows a P/B-based target (peer average P/B × book value per share) as a cross-check. It matters most for banks.
- If the score says Buy but the target is below today's price (or Sell with >10% upside), the report flags it for your review.

### Projections: analysts first, then the tool

Every report puts two projections side by side:
1. **Analyst projection:** the consensus (average) analyst target, the low–high range, the number of analysts and their consensus rating.
2. **Tool projection:** the peer P/E target above.

It flags when the tool's target is more than 15% away from the analysts' target, or when the two point in opposite directions.

### Drawdown vs the sector at the same time

The tool finds the stock's worst peak-to-trough fall (month-end closes) and the months it ran between. Over those same months, it shows how each peer moved and how an equal-weighted index of the peers moved. **Stock vs sector** = stock's fall − sector's move over the same window. A large negative number means the fall was company-specific, not the whole sector. It flags anything more than 10 points worse than the sector.

### Sector rank

Every company is also scored against all the others in its group, so each report shows its rank (e.g., **#2 of 6**). The sector page ranks the whole group.

### Published vs calculated

Anything a site publishes in a standard form is used as published: P/E, P/B, margins, ROE, payout, beta, CET1. Only the figures the method defines are calculated: 3-year CAGR, 5-year Sharpe, 5-year max drawdown, upside. Each one is calculated from published prices with a single formula. Websites use different windows (e.g., PortfoliosLab shows RY's Sharpe over 1 year and its max drawdown back to 2009), so calculating these keeps every company on the same 5-year window.

### How each ratio is calculated

| Metric | Formula | Source |
|---|---|---|
| P/E (trailing / forward) | Price ÷ EPS (last 12 mo / next FY estimate) | Yahoo Finance |
| EV/EBITDA | (Market cap + debt − cash) ÷ EBITDA | Yahoo Finance |
| P/B | Price ÷ book value per share | Yahoo Finance |
| Net / operating margin | Net / operating income ÷ revenue | Yahoo Finance |
| ROE | Net income ÷ shareholders' equity | Yahoo Finance |
| Debt-to-equity | Total debt ÷ equity | Yahoo Finance |
| FCF yield | Free cash flow ÷ market cap | Yahoo Finance |
| 3-yr CAGR | (Latest ÷ 3 yrs ago)^(1/3) − 1 | Annual income statement |
| Beta | Cov(stock, TSX) ÷ Var(TSX), 60 monthly returns | Calculated (`tool/calcs.py`) |
| Sharpe | (Annual return − T-bill) ÷ annual volatility | Calculated, risk-free = 3-mo T-bill |
| Max drawdown | Lowest (price ÷ running peak − 1) over 5 yrs | Calculated |
| Dividend yield | Dividends paid last 12 mo ÷ price | Calculated |
| Payout ratio | Dividends per share ÷ EPS | Calculated |
| CET1 ratio | CET1 capital ÷ risk-weighted assets | Entered by hand from bank reports (`bank_cet1.json`) |

---

## Files

| File | What it is |
|---|---|
| `research.py` | Entry point: run this |
| `config.json` | Weights, thresholds, sector rules, risk-free rate. **All judgment calls live here.** |
| `peers.json` | Peer groups (Big Six banks, energy, pipelines, telecom, etc.) |
| `bank_cet1.json` | CET1 ratios for the Big Six (Q3 FY2026). Update every quarter. |
| `tool/data.py` | Pulls data from Yahoo Finance |
| `tool/webdata.py` | Reads a web-collected data file (`data/*.json`) instead |
| `data/` | Saved web data, e.g. the Canadian banks run of 2026-10-16 |
| `tool/calcs.py` | CAGR, beta, Sharpe, max drawdown: plain formulas |
| `tool/analysis.py` | Scoring, the call, target price |
| `tool/rationale.py` | 150-word rationale (template or Claude) |
| `tool/report.py` | HTML/JSON report and terminal summary |
| `tests/test_offline.py` | Checks the math on made-up numbers, no internet needed |

## Before your showcase run

- Update `risk_free_rate` in `config.json` to the current 3-month T-bill yield (it was 2.40% on 2026-10-14).
- For a bank, check that `bank_cet1.json` has the latest quarter. Q4 FY2026 results come out in early December.
- Open the report and check 3–4 key numbers (P/E, ROE, CET1 or D/E, dividend yield) against the company's annual report or investor deck. Fill in the "My review" section with where you agree with the tool and where you'd override it.

## Known limits

- Yahoo Finance data is free and generally reliable, but it does sometimes have gaps or stale fields. Anything missing is shown as "n/a", left out of the score, and listed under Flags.
- A 3-year CAGR can't be calculated from a loss. Those cases show "n/a".
- Peer groups are hand-picked. If the company you test isn't covered, pass `--peers`.

---

## Added 2026-10-21: three upgrades

| Upgrade | How to use | What it does |
|---|---|---|
| **Live risk-free rate** | Automatic on every live run (`"auto_risk_free": true` in `config.json`) | Pulls the Bank of Canada 3-month T-bill yield (series V80691344, free, no key) for the Sharpe ratio. If the Bank can't be reached, it uses `risk_free_rate` from `config.json` and says so. The source is listed under Flags in each report. `--data` runs keep the config value so saved runs stay reproducible. |
| **Auto-picked peers** | `pip install financedatabase`, then `python research.py <any TSX ticker>` | If the ticker isn't in `peers.json`, peers are suggested from FinanceDatabase: same industry, same exchange, closest size, preferred shares dropped. The report flags that they were auto-picked. Check them or pass `--peers`. Industries are broad (Suncor's group also holds pipelines and Cameco). |
| **TMX cross-check** | `pip install openbb-core openbb-tmx`, then add `--crosscheck` | Compares Yahoo's price, market cap, P/E, P/B, dividend yield and ROE with TMX's. Scores never change; any gap beyond the tolerance in `tool/crosscheck.py` shows up under Flags as a number to check against the company's filings. Skipped quietly if TMX can't be reached. |

Not yet run against the live Bank of Canada and TMX sites (the build environment couldn't reach them), so run once with internet and check the Flags section.
