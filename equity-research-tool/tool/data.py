"""
Pulls the raw numbers for one company from Yahoo Finance (free, via the yfinance library)
and turns them into a flat "snapshot" dictionary that the scoring step reads.

Every field in the snapshot is listed in SNAPSHOT_FIELDS below with what it means.
"""
import json
import math
import os
from datetime import datetime, timedelta

import pandas as pd

from . import calcs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SNAPSHOT_FIELDS = {
    "pe_trailing":      "Price / last 12 months' EPS",
    "pe_forward":       "Price / analysts' expected EPS for the next fiscal year",
    "ev_ebitda":        "Enterprise value / EBITDA",
    "pb":               "Price / book value per share",
    "net_margin":       "Net income / revenue (last 12 months)",
    "operating_margin": "Operating income / revenue (last 12 months)",
    "roe":              "Net income / shareholders' equity (last 12 months)",
    "debt_to_equity":   "Total debt / shareholders' equity (1.5 = 150%)",
    "fcf_yield":        "Free cash flow / market cap",
    "revenue_cagr_3y":  "Compound annual revenue growth over the last 3 fiscal years",
    "eps_cagr_3y":      "Compound annual diluted-EPS growth over the last 3 fiscal years",
    "beta":             "Beta vs the S&P/TSX Composite, 5 yrs of monthly returns",
    "sharpe":           "(Annual return - risk-free rate) / annual volatility, 5 yrs monthly",
    "max_drawdown":     "Worst peak-to-trough fall over 5 yrs (negative number)",
    "dividend_yield":   "Dividends paid in the last 12 months / current price",
    "payout_ratio":     "Dividends per share / EPS, last 12 months",
    "cet1_ratio":       "Common Equity Tier 1 capital / risk-weighted assets (banks only, entered by hand)",
}


def _load_json(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def _num(x):
    """Return a clean float, or None for missing / NaN / non-numeric."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def _first_row(df, names):
    """First matching row from a yfinance statement, oldest year first."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            s = df.loc[n].dropna()
            if not s.empty:
                return s.sort_index()
    return None


def _three_year_cagr(series, notes, label):
    """CAGR across the last 4 annual data points (= 3 years of growth)."""
    if series is None or len(series) < 2:
        notes.append(f"{label}: not enough annual history")
        return None, None
    pts = series.iloc[-4:]
    years = len(pts) - 1
    if years < 3:
        notes.append(f"{label}: only {years} yrs of history available, CAGR uses {years} yrs")
    g = calcs.cagr(_num(pts.iloc[0]), _num(pts.iloc[-1]), years)
    if g is None:
        notes.append(f"{label}: start or end value is zero/negative, CAGR not meaningful")
    hist = {str(d.date() if hasattr(d, "date") else d): _num(v) for d, v in pts.items()}
    return g, hist


# ---------------------------------------------------------------- ticker lookup

def resolve_ticker(query, default_suffix=".TO"):
    """Turn 'RY', 'RY.TO', or 'Royal Bank of Canada' into a Yahoo ticker that has prices."""
    import yfinance as yf

    q = query.strip()
    looks_like_ticker = " " not in q and len(q) <= 12
    if looks_like_ticker:
        candidates = [q.upper()] if ("." in q or q.startswith("^")) else [q.upper() + default_suffix, q.upper()]
        for c in candidates:
            try:
                if not yf.Ticker(c).history(period="5d").empty:
                    return c
            except Exception:
                pass

    # Fall back to a name search, preferring Toronto listings.
    try:
        quotes = yf.Search(q, max_results=10).quotes
    except Exception:
        quotes = []
    equities = [x for x in quotes if x.get("quoteType") == "EQUITY"]
    for x in equities:
        if x.get("symbol", "").endswith(default_suffix):
            return x["symbol"]
    if equities:
        return equities[0]["symbol"]
    raise ValueError(f"Couldn't find a listed stock for '{query}'. Try the exact ticker, e.g. RY.TO")


# ---------------------------------------------------------------- snapshot

_benchmark_cache = {}


def _price_history(ticker, years):
    import yfinance as yf
    h = yf.Ticker(ticker).history(period=f"{years}y", auto_adjust=True)
    return h["Close"] if not h.empty else pd.Series(dtype=float)


def benchmark_prices(cfg):
    key = (cfg["risk"]["benchmark"], cfg["risk"]["lookback_years"])
    if key not in _benchmark_cache:
        _benchmark_cache[key] = _price_history(*key)
    return _benchmark_cache[key]


def detect_sector(info, ticker, peers_cfg):
    if ticker in peers_cfg.get("canadian_banks", []):
        return "bank"
    if "bank" in (info.get("industry") or "").lower():
        return "bank"
    if (info.get("sector") or "").lower() == "energy":
        return "energy"
    return "default"


_fx_cache = {}


def get_fx_rate(from_ccy, to_ccy):
    """Latest close of the Yahoo FX pair, e.g. USD->CAD from "USDCAD=X". None if unavailable."""
    if from_ccy == to_ccy:
        return 1.0
    key = (from_ccy, to_ccy)
    if key not in _fx_cache:
        rate = None
        try:
            import yfinance as yf
            h = yf.Ticker(f"{from_ccy}{to_ccy}=X").history(period="5d")
            if not h.empty:
                rate = _num(h["Close"].iloc[-1])
        except Exception:
            rate = None
        _fx_cache[key] = rate if rate and rate > 0 else None
    return _fx_cache[key]


def fetch_snapshot(ticker, cfg):
    """Everything the scoring step needs for one company, as a plain dictionary."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = t.info or {}
    notes = []

    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
    if price is None:
        h = t.history(period="5d")
        price = _num(h["Close"].iloc[-1]) if not h.empty else None
    if price is None:
        raise ValueError(f"No price data for {ticker}")

    mcap = _num(info.get("marketCap"))
    pe_t = _num(info.get("trailingPE"))
    pe_f = _num(info.get("forwardPE"))
    pb = _num(info.get("priceToBook"))

    # Yahoo gives some fields in the reporting currency (e.g. USD for a TSX stock that reports in USD).
    # Backing EPS out of price / P/E keeps everything in the trading currency.
    fin_ccy, px_ccy = info.get("financialCurrency"), info.get("currency")
    if fin_ccy and px_ccy and fin_ccy != px_ccy:
        notes.append(f"Reports in {fin_ccy} but trades in {px_ccy}; EPS figures derived from price / P/E to stay in {px_ccy}")
    eps_ttm = price / pe_t if pe_t and pe_t > 0 else _num(info.get("trailingEps"))
    eps_fwd = price / pe_f if pe_f and pe_f > 0 else _num(info.get("forwardEps"))
    if pe_t is None and eps_ttm and eps_ttm > 0:
        pe_t = price / eps_ttm

    d2e = _num(info.get("debtToEquity"))
    d2e = d2e / 100 if d2e is not None else None  # Yahoo reports 150 for 150%

    fcf = _num(info.get("freeCashflow"))
    fx_used = None
    if fcf is not None and fin_ccy and px_ccy and fin_ccy != px_ccy:
        # Free cash flow is in the reporting currency, market cap in the trading currency.
        # Convert before dividing; if no rate is available, leave the metric out rather than score a wrong ratio.
        rate = get_fx_rate(fin_ccy, px_ccy)
        if rate:
            fx_used = {"pair": f"{fin_ccy}{px_ccy}", "rate": rate}
            notes.append(f"FCF converted {fin_ccy}->{px_ccy} at {rate:.4f} before computing FCF yield")
            fcf = fcf * rate
        else:
            notes.append(f"FCF yield excluded: no FX rate {fin_ccy}->{px_ccy}")
            fcf = None
    fcf_yield = fcf / mcap if (fcf is not None and mcap) else None

    # 3-year growth from the annual income statement
    try:
        inc = t.income_stmt
    except Exception:
        inc = None
    rev = _first_row(inc, ["Total Revenue", "Operating Revenue"])
    eps = _first_row(inc, ["Diluted EPS", "Basic EPS"])
    rev_g, rev_hist = _three_year_cagr(rev, notes, "Revenue growth")
    eps_g, eps_hist = _three_year_cagr(eps, notes, "EPS growth")

    # Dividends actually paid over the last 12 months
    try:
        divs = t.dividends
        if getattr(divs.index, "tz", None) is not None:
            divs.index = divs.index.tz_localize(None)
        dps = float(divs[divs.index >= datetime.now() - timedelta(days=365)].sum())
    except Exception:
        dps = None
    if dps is None:
        dps = _num(info.get("trailingAnnualDividendRate")) or 0.0
    div_yield = dps / price if price else None
    if dps == 0:
        payout = None
    elif eps_ttm and eps_ttm > 0:
        payout = dps / eps_ttm
    else:
        payout = _num(info.get("payoutRatio"))

    # Risk, from 5 years of total-return prices
    years = cfg["risk"]["lookback_years"]
    px = _price_history(ticker, years)
    bench = benchmark_prices(cfg)
    b = calcs.beta(px, bench) if not px.empty and not bench.empty else None
    sh = calcs.sharpe(px, cfg["risk"]["risk_free_rate"]) if not px.empty else None
    mdd = calcs.max_drawdown(px) if not px.empty else None
    if not px.empty:
        span = (px.index[-1] - px.index[0]).days / 365.25
        if span < years - 0.5:
            notes.append(f"Only {span:.1f} yrs of price history; risk ratios use what's available")

    peers_cfg = _load_json("peers.json")
    sector = detect_sector(info, ticker, peers_cfg)
    cet1 = None
    if sector == "bank":
        cet1_cfg = _load_json("bank_cet1.json")
        entry = cet1_cfg.get(ticker)
        if entry:
            cet1 = entry["cet1"]
        else:
            notes.append("CET1 ratio not in bank_cet1.json; add it from the bank's latest quarterly report")

    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName") or ticker,
        "sector": sector,
        "yahoo_sector": info.get("sector"),
        "industry": info.get("industry"),
        "currency": px_ccy,
        "price": price,
        "market_cap": mcap,
        "eps_ttm": eps_ttm,
        "eps_forward": eps_fwd,
        "book_value_per_share": price / pb if pb and pb > 0 else None,
        "dps_ttm": dps,
        "pe_trailing": pe_t,
        "pe_forward": pe_f,
        "ev_ebitda": _num(info.get("enterpriseToEbitda")),
        "pb": pb,
        "net_margin": _num(info.get("profitMargins")),
        "operating_margin": _num(info.get("operatingMargins")),
        "roe": _num(info.get("returnOnEquity")),
        "debt_to_equity": d2e,
        "fcf_yield": fcf_yield,
        "fx_used": fx_used,
        "revenue_cagr_3y": rev_g,
        "eps_cagr_3y": eps_g,
        "revenue_history": rev_hist,
        "eps_history": eps_hist,
        "beta": b,
        "sharpe": sh,
        "max_drawdown": mdd,
        "dividend_yield": div_yield,
        "payout_ratio": payout,
        "cet1_ratio": cet1,
        "analyst": {
            "rating": info.get("recommendationKey"),
            "count": info.get("numberOfAnalystOpinions"),
            "target_mean": _num(info.get("targetMeanPrice")),
            "target_low": _num(info.get("targetLowPrice")),
            "target_high": _num(info.get("targetHighPrice")),
            "source": "Yahoo Finance consensus",
        },
        "monthly_prices": ({str(k): float(v) for k, v in calcs.to_monthly(px).items()} if not px.empty else None),
        "notes": notes,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def find_peers(ticker, cfg, override=None):
    if override:
        return [p.strip().upper() for p in override if p.strip().upper() != ticker][: cfg["max_peers"]]
    groups = _load_json("peers.json")
    for name, members in groups.items():
        if name.startswith("_"):
            continue
        if ticker in members:
            return [m for m in members if m != ticker][: cfg["max_peers"]]
    raise ValueError(
        f"{ticker} isn't in any peer group in peers.json. Pass peers yourself, "
        f"e.g. --peers RY.TO,TD.TO,BNS.TO"
    )
