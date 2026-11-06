"""Display names and number formatting shared by the report and the rationale."""
import math

METRIC_NAMES = {
    "pe_trailing": "P/E (trailing)",
    "pe_forward": "P/E (forward)",
    "ev_ebitda": "EV/EBITDA",
    "pb": "P/B",
    "net_margin": "Net margin",
    "operating_margin": "Operating margin",
    "roe": "ROE",
    "debt_to_equity": "Debt-to-equity",
    "fcf_yield": "FCF yield",
    "revenue_cagr_3y": "3-yr revenue growth (CAGR)",
    "eps_cagr_3y": "3-yr EPS growth (CAGR)",
    "beta": "Beta vs TSX",
    "sharpe": "Sharpe ratio",
    "max_drawdown": "Max drawdown (5 yr)",
    "dividend_yield": "Dividend yield",
    "payout_ratio": "Payout ratio",
    "cet1_ratio": "CET1 ratio",
}

_PCT = {"net_margin", "operating_margin", "roe", "fcf_yield", "revenue_cagr_3y", "eps_cagr_3y",
        "max_drawdown", "dividend_yield", "payout_ratio", "cet1_ratio"}
_MULT = {"pe_trailing", "pe_forward", "ev_ebitda", "pb", "debt_to_equity"}


def metric(name, v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "n/a"
    if name in _PCT:
        return f"{v * 100:.1f}%"
    if name in _MULT:
        return f"{v:.1f}x"
    return f"{v:.2f}"


def money(v):
    return "n/a" if v is None else f"${v:,.2f}"


def pct(v, signed=True):
    if v is None:
        return "n/a"
    return f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"
