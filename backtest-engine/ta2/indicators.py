"""Indicator formulas (Wilder smoothing = TradingView ta.rsi/ta.atr/ta.dmi) + the per-stock context. From tsxta v1.

Every function takes a DataFrame with open/high/low/close/volume columns and
returns a Series. Wilder smoothing is used where the original definition uses it,
so values should match TradingView's built-ins (ta.rsi, ta.atr, ta.dmi).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average (TradingView ta.rma)."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df.close.shift()
    return pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up, dn = rma(d.clip(lower=0), n), rma(-d.clip(upper=0), n)
    return 100 - 100 / (1 + up / dn)


def dmi(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up, dn = df.high.diff(), -df.low.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = rma(true_range(df), n)
    pdi = 100 * rma(pd.Series(plus_dm, index=df.index), n) / tr
    mdi = 100 * rma(pd.Series(minus_dm, index=df.index), n) / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return pd.DataFrame({"plus_di": pdi, "minus_di": mdi, "adx": rma(dx, n)})


def macd(s: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9) -> pd.DataFrame:
    m = ema(s, fast) - ema(s, slow)
    sg = ema(m, sig)
    return pd.DataFrame({"macd": m, "signal": sg, "hist": m - sg})


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid, sd = sma(s, n), s.rolling(n).std(ddof=0)
    up, lo = mid + k * sd, mid - k * sd
    return pd.DataFrame({"mid": mid, "upper": up, "lower": lo, "pctb": (s - lo) / (up - lo)})


def obv(df: pd.DataFrame) -> pd.Series:
    return (np.sign(df.close.diff()).fillna(0) * df.volume).cumsum()


def donchian(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return pd.DataFrame({"upper": df.high.rolling(n).max(), "lower": df.low.rolling(n).min()})


def streak(s: pd.Series) -> pd.Series:
    """Consecutive up (+) or down (-) closes."""
    sign = np.sign(s.diff()).fillna(0)
    grp = (sign != sign.shift()).cumsum()
    return sign * sign.groupby(grp).cumcount().add(1)


def regime(df: pd.DataFrame, hi: float = 25, lo: float = 20) -> pd.Series:
    """ADX regime: 'trend' above 25, 'range' below 20, else 'transition' [M ch 15]."""
    a = dmi(df).adx
    return pd.Series(np.select([a > hi, a < lo], ["trend", "range"], "transition"), index=df.index).where(a.notna())


def add_all(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out.close
    out["sma20"], out["sma50"], out["sma200"] = sma(c, 20), sma(c, 50), sma(c, 200)
    out["atr14"] = atr(out)
    out["rsi14"] = rsi(c)
    out = out.join(dmi(out))
    out = out.join(macd(c))
    out["stretch_atr"] = (c - out.sma20) / out.atr14
    out["vol_ratio"] = out.volume / out.volume.rolling(10).mean().shift()
    out["streak"] = streak(c)
    out["regime"] = regime(out)
    out["trend_up"] = (c > out.sma200) & (out.sma200 > out.sma200.shift(20))
    return out


def stoch_k(df: pd.DataFrame, n: int = 14, smooth: int = 3) -> pd.Series:
    ll, hh = df.low.rolling(n).min(), df.high.rolling(n).max()
    return (100 * (df.close - ll) / (hh - ll)).rolling(smooth).mean()


def context(df: pd.DataFrame, earn_dates=None) -> dict:
    """Arrays every strategy can use (same as v1 run.context). All causal (known at the bar's close)."""
    c = df.close
    bb = bollinger(c); d = dmi(df)
    ed = pd.Series([] if earn_dates is None else earn_dates, dtype="datetime64[ns]")
    epos = np.array(sorted(set(df.index.searchsorted(ed))), dtype=np.int64) if len(ed) else np.array([], np.int64)
    estart = int(df.index.searchsorted(ed.min())) if len(ed) else 10 ** 9
    return dict(atr=atr(df).values, rsi=rsi(c).values, adx=d.adx.values, pdi=d.plus_di.values, mdi=d.minus_di.values,
                stk=stoch_k(df).values, bbl=bb.lower.values, bbu=bb.upper.values,
                vol10=df.volume.rolling(10).mean().shift(1).values,
                hi252=df.high.rolling(252, min_periods=60).max().shift(1).values,
                lo252=df.low.rolling(252, min_periods=60).min().shift(1).values,
                sma={n: c.rolling(n).mean().values for n in (10, 20, 50, 100, 150, 200)},
                epos=epos, estart=estart)


def no_earn(ctx, t, before=1, after=10):
    """True if no earnings date from `before` bars before t to `after` bars after t (True before coverage starts)."""
    t = np.asarray(t, dtype=np.int64); ep = ctx["epos"]
    if len(ep) == 0:
        return np.ones(len(t), bool)
    i = np.searchsorted(ep, t - before)
    nxt = np.where(i < len(ep), ep[np.minimum(i, len(ep) - 1)], 10 ** 9)
    return np.where(t < ctx["estart"], True, nxt > t + after)
