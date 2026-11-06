"""Shared bits for PEADU / PEADB (post-earnings drift and bounce). Claude, 2026-11-05.
Event E = first session on/after the saved earnings date (same convention as EARN).
Reaction R2 = close(E+1)/close(E-1) - 1, size = |R2| / (ATR20(E-1)/close(E-1))."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .earn import attach_earnings, prepare_earnings  # noqa: F401  (Prep hook: loads earnings dates)

EXITS = {"time20": 20, "time40": 40, "time60": 60}


def events(df, ctx):
    """(E index array, R2 array, size array) for every earnings event with E-1 and E+1 inside the data."""
    if "earn_signal_dates" not in ctx:
        raise ValueError("needs prepare_earnings(prep) (sweep.Prep calls it automatically)")
    c = df.close.to_numpy(float); a = np.asarray(ctx["atr"], float)
    e1 = df.index.get_indexer(pd.DatetimeIndex(ctx["earn_signal_dates"]))      # E-1 positions
    e1 = np.unique(e1[e1 >= 0]); E = e1 + 1
    E = E[E + 1 < len(c)]
    r2 = c[E + 1] / c[E - 1] - 1
    atrp = a[E - 1] / c[E - 1]
    size = np.abs(r2) / np.where(atrp > 0, atrp, np.nan)
    ok = np.isfinite(r2) & np.isfinite(size)
    return E[ok], r2[ok], size[ok]


def exit_recipe(k):
    e = k["exit"]
    if e in EXITS:
        return dict(time_bars=EXITS[e], max_hold=EXITS[e] + 5)
    return dict(trail_atr=3.0, max_hold=60)


def lines(df, ctx, k):
    return {}
