"""
The math, kept in plain functions so each one can be checked by hand.

Every function here takes simple numbers or a price series and returns one number.
Nothing here talks to the internet.
"""
import math

import numpy as np
import pandas as pd


def cagr(first, last, years):
    """Compound annual growth rate: (last / first) ^ (1 / years) - 1.

    Returns None when either end is zero or negative, because growth from a loss
    (or into a loss) has no meaningful compound rate. The report shows "n/a".
    """
    if first is None or last is None or years <= 0:
        return None
    if first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def to_monthly(prices: pd.Series) -> pd.Series:
    """Month-end closing prices from a daily price series."""
    s = prices.dropna().copy()
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    return s.groupby(s.index.to_period("M")).last()


def monthly_returns(prices: pd.Series) -> pd.Series:
    return to_monthly(prices).pct_change().dropna()


def beta(stock_prices: pd.Series, index_prices: pd.Series):
    """Beta vs the index from monthly returns: covariance(stock, index) / variance(index).

    Beta 1.0 = moves with the TSX; 0.7 = moves 70% as much; 1.3 = 30% more.
    """
    s = monthly_returns(stock_prices)
    m = monthly_returns(index_prices)
    both = pd.concat([s, m], axis=1, join="inner").dropna()
    if len(both) < 24:  # need at least two years of months to be meaningful
        return None
    cov = np.cov(both.iloc[:, 0], both.iloc[:, 1], ddof=1)[0, 1]
    var = np.var(both.iloc[:, 1], ddof=1)
    return float(cov / var) if var else None


def sharpe(stock_prices: pd.Series, risk_free_rate: float):
    """Sharpe ratio = (annual return - risk-free rate) / annual volatility.

    Annual return = average monthly return x 12.
    Annual volatility = standard deviation of monthly returns x sqrt(12).
    Uses total-return prices (dividends reinvested) so dividend payers aren't penalised.
    """
    r = monthly_returns(stock_prices)
    if len(r) < 24:
        return None
    ann_ret = r.mean() * 12
    ann_vol = r.std(ddof=1) * math.sqrt(12)
    return float((ann_ret - risk_free_rate) / ann_vol) if ann_vol else None


def max_drawdown(prices: pd.Series):
    """Largest peak-to-trough fall over the period, as a negative number (e.g. -0.32 = -32%).

    At each day: drawdown = price / highest price so far - 1. Max drawdown = the lowest of those.
    """
    p = prices.dropna()
    if p.empty:
        return None
    running_peak = p.cummax()
    dd = p / running_peak - 1
    return float(dd.min())


def annualised_return(prices: pd.Series):
    p = prices.dropna()
    if len(p) < 2:
        return None
    years = (p.index[-1] - p.index[0]).days / 365.25
    if years <= 0 or p.iloc[0] <= 0:
        return None
    return float((p.iloc[-1] / p.iloc[0]) ** (1 / years) - 1)


def drawdown_window(prices: pd.Series):
    """Max drawdown plus when it happened: (drawdown, peak_date, trough_date)."""
    p = prices.dropna()
    if len(p) < 2:
        return None, None, None
    dd = p / p.cummax() - 1
    trough = dd.idxmin()
    peak = p.loc[:trough].idxmax()
    return float(dd.min()), peak, trough
