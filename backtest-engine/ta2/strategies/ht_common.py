"""Shared helpers for the Humbled Trader (Shay) strategy files HT1-HT3 (2026-11-03).

Look-ahead rule for open / order entries (modes 2 and 3): a signal on bar t may use bar t's OPEN and anything up to
bar t-1. Bar t's high/low may only be used to decide whether a resting order would have filled, never for the stop.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from numba import njit
from .. import data as D

_IDX = {}


def index_bars(df, ctx):
    """Index ETF bars aligned to df's dates (XIU.TO for TSX, SPY for US): open, close, sma200 arrays."""
    uni = ctx.get("universe", "TSX")
    key = "SPY" if uni == "US" else "XIU.TO"
    if key not in _IDX:
        x = None
        for ho in (True, False):
            try:
                x = D.load(key, uni, ho)
                if x is not None and len(x):
                    break
            except Exception:
                x = None
        _IDX[key] = x
    x = _IDX[key]
    if x is None or not len(x):
        nan = np.full(len(df), np.nan)
        return dict(o=nan, c=nan, sma200=nan)
    y = pd.DataFrame(dict(o=x.open, c=x.close, sma200=x.close.rolling(200).mean())).reindex(df.index)
    return {k: y[k].to_numpy(float) for k in y}


def up_streak(c):
    """+k = k consecutive up closes ending at this bar, -k = k down closes."""
    d = np.sign(np.diff(c, prepend=np.nan)); out = np.zeros(len(c))
    for i in range(1, len(c)):
        if d[i] > 0:
            out[i] = out[i - 1] + 1 if out[i - 1] > 0 else 1
        elif d[i] < 0:
            out[i] = out[i - 1] - 1 if out[i - 1] < 0 else -1
    return out


@njit(cache=True)
def levels(h, l, look, gap, tol):
    """Resistance / support from the window [t-look, t-gap] (bars before t only).
    res[t] = highest high there, rtouch[t] = separate touches (bars with high within tol of it, a new touch
    only after a bar that was not touching). Same for support with lows."""
    n = len(h)
    res = np.full(n, np.nan); sup = np.full(n, np.nan)
    rt = np.zeros(n, np.int64); st = np.zeros(n, np.int64)
    for t in range(look, n):
        a = t - look; b = t - gap + 1
        R = -1e18; S = 1e18
        for j in range(a, b):
            if h[j] > R: R = h[j]
            if l[j] < S: S = l[j]
        cr = 0; cs = 0; inr = False; ins = False
        for j in range(a, b):
            if h[j] >= R * (1 - tol):
                if not inr: cr += 1
                inr = True
            else:
                inr = False
            if l[j] <= S * (1 + tol):
                if not ins: cs += 1
                ins = True
            else:
                ins = False
        res[t] = R; sup[t] = S; rt[t] = cr; st[t] = cs
    return res, rt, sup, st


def is_earn(ctx, n):
    """Bool array: an earnings date falls on this bar or the bar before (pre-market or after-close report)."""
    e = np.zeros(n, bool); ep = ctx["epos"]
    ep = ep[(ep >= 0) & (ep < n)]
    e[ep] = True
    e[np.minimum(ep + 1, n - 1)] = True
    return e


def common_lines(df, side):
    c = df.close.astype(float)
    ema8 = c.ewm(span=8, adjust=False, min_periods=8).mean()
    return {"ema8": (c - ema8).to_numpy(float),
            "pdl": (c - df.low.shift()).to_numpy(float),     # long: exit on a close below the prior-day low
            "neg": np.full(len(c), -float(side))}                    # exit at the very next open (overnight hold)
