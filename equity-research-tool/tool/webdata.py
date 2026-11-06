"""
Builds snapshots from a hand-collected data file (data/*.json) instead of Yahoo Finance.

Used when the tool runs somewhere that can't reach Yahoo (e.g. the cloud). The snapshot it
returns has exactly the same fields as data.fetch_snapshot, so scoring works the same way.

Price multiples are recalculated at the latest close so every company is measured on the
same day:  P/E = price / EPS,  P/B = price / book value per share,  yield = dividend / price.
"""
import json
import os

import pandas as pd

from . import calcs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_snapshots(path, cfg):
    with open(path, encoding="utf-8") as f:
        src = json.load(f)
    with open(os.path.join(ROOT, "bank_cet1.json"), encoding="utf-8") as f:
        cet1 = json.load(f)
    sector = src.get("sector", "default")
    months = cfg["risk"]["lookback_years"] * 12
    snaps = []
    for ticker, d in src["companies"].items():
        notes = list(src.get("notes", {}).get(ticker, []))
        px = None
        if d.get("monthly_adj_close"):
            s = pd.Series(d["monthly_adj_close"])
            s.index = pd.to_datetime(s.index)
            px = s.sort_index().iloc[-(months + 1):]          # 60 monthly returns = 61 prices
            price = float(px.iloc[-1])
            price_note = f"latest close {px.index[-1]:%b %Y}"
        else:
            price = d["page_price"]
            price_note = f"stats page price ({d['page_date']})"
            notes.append("No price history collected: Sharpe ratio and max drawdown not available")

        eps_fwd = d["page_price"] / d["pe_fwd_page"]
        rev, eps = d["revenue"], d["eps"]
        rev_g = calcs.cagr(rev[0], rev[-1], len(rev) - 1)
        eps_g = calcs.cagr(eps[0], eps[-1], len(eps) - 1)
        if eps_g is None:
            notes.append("EPS growth: start or end value is zero/negative, CAGR not meaningful")
        if (d.get("page_date") and d["page_date"] < src.get("collected", "")[:7] + "-01"
                and not any("Ratios page" in n for n in notes)):
            notes.append(f"Ratios page last updated {d['page_date']}; margins/ROE may lag one quarter")

        mdd = calcs.max_drawdown(px) if px is not None else None
        sh = calcs.sharpe(px, cfg["risk"]["risk_free_rate"]) if px is not None else None
        if px is not None:
            notes.append("Max drawdown and Sharpe from month-end closes (a daily-price drawdown would be somewhat deeper)")
        notes.append("Beta: stockanalysis.com published 5Y beta")

        c1 = cet1.get(ticker, {}).get("cet1") if sector == "bank" else None
        snaps.append({
            "ticker": ticker,
            "name": d["name"],
            "sector": sector,
            "industry": "Banks - Diversified" if sector == "bank" else d.get("industry"),
            "currency": d.get("currency", "CAD"),
            "price": price,
            "price_basis": price_note,
            "market_cap": None,
            "eps_ttm": d["eps_ttm"],
            "eps_forward": eps_fwd,
            "book_value_per_share": d["bvps"],
            "dps_ttm": d["dps"],
            "pe_trailing": price / d["eps_ttm"] if d["eps_ttm"] > 0 else None,
            "pe_forward": price / eps_fwd if eps_fwd > 0 else None,
            "ev_ebitda": d.get("ev_ebitda"),
            "pb": price / d["bvps"],
            "net_margin": d["net_margin"],
            "operating_margin": d["operating_margin"],
            "roe": d["roe"],
            "debt_to_equity": d.get("debt_to_equity"),
            # FCF yield moves inversely with price: page yield x (page price / latest price)
            "fcf_yield": d["fcf_yield_page"] * d["page_price"] / price if d.get("fcf_yield_page") is not None else None,
            "revenue_cagr_3y": rev_g,
            "eps_cagr_3y": eps_g,
            "revenue_history": dict(zip(d["fy"], rev)),
            "eps_history": dict(zip(d["fy"], eps)),
            "beta": d["beta"],
            "sharpe": sh,
            "max_drawdown": mdd,
            "dividend_yield": d["dps"] / price,
            "payout_ratio": d.get("payout"),
            "cet1_ratio": c1,
            "analyst": d.get("analyst"),
            "monthly_prices": ({k.strftime("%Y-%m"): float(v) for k, v in px.items()} if px is not None else None),
            "notes": notes,
            "fetched_at": f"web data collected {src.get('collected')}",
        })
    return snaps
