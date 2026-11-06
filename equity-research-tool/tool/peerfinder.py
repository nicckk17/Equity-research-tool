"""
Suggests peers for a TSX ticker that isn't in peers.json, using the FinanceDatabase package
(pip install financedatabase). It matches on the same industry, same exchange, and the closest
market-cap size bucket. Preferred shares are dropped.

These are SUGGESTIONS. FinanceDatabase's industries are broad (Suncor's "Oil, Gas & Fuels" also
holds pipelines), so check the list or pass your own with --peers.
"""
import re

CAP_ORDER = ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]
PREFERRED = re.compile(r"-P[A-Z]{0,2}\.TO$")   # e.g. ENB-PA.TO, TRP-PD.TO


def _cap_rank(v):
    return CAP_ORDER.index(v) if v in CAP_ORDER else 3


def pick(df, ticker, max_peers):
    """Pure function over a FinanceDatabase table, so it can be tested offline. Returns (peers, why)."""
    if ticker not in df.index:
        raise ValueError(f"{ticker} not found in FinanceDatabase")
    me = df.loc[ticker]
    base = df[(df["exchange"] == me["exchange"]) & (~df.index.isin([ticker]))]
    base = base[[not PREFERRED.search(i) for i in base.index]]
    if "delisted" in base.columns:
        base = base[base["delisted"] != True]  # noqa: E712
    same = base[base["industry"] == me["industry"]]
    level = f"industry '{me['industry']}'"
    if len(same) < 3:
        same = base[base["industry_group"] == me["industry_group"]]
        level = f"industry group '{me['industry_group']}'"
    me_rank = _cap_rank(me["market_cap"])
    ranked = sorted(same.index, key=lambda i: (abs(_cap_rank(same.loc[i, "market_cap"]) - me_rank), i))
    return ranked[:max_peers], f"{level}, {me['market_cap']} size, {me['exchange']} exchange"


def suggest(ticker, max_peers=5):
    """Load FinanceDatabase and return (peers, description). Raises if the package is missing."""
    import financedatabase as fd
    df = fd.Equities().select(country="Canada")
    return pick(df, ticker, max_peers)
