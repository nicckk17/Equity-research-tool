"""EAP: earnings announcement premium (Frazzini & Lamont 2007). Long from `pre` sessions before the scheduled
earnings day E to `post` sessions after, no direction call. Claude, 2026-11-05.
Signal bar t = E - pre - 1 (the date is scheduled in advance, same convention as EARN/PEADU); entry next open
(mode 1) or that close (mode 0); exit by time after pre+post+1 bars; a wide ATR stop is required by the engine."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ..knobs import Knob
from .earn import attach_earnings, prepare_earnings  # noqa: F401  (Prep hook loads earnings dates)

KEY, NAME, SIDE = "EAP", "Earnings announcement premium (long around earnings)", 1
TIMEFRAMES, EPISODE_GAP = ["D"], 1
KNOBS = {
    "pre":      Knob(10, [3, 5, 10, 15], "signal", "sessions before E to enter"),
    "post":     Knob(2, [0, 2, 5, 10], "exit", "sessions after E to exit"),
    "stop_atr": Knob(5, [3, 5, 8], "stop", "stop = close(t) - k x ATR"),
    "trend200": Knob(False, [False, True], "filter", "close above 200 SMA"),
    "mode":     Knob(1, [0, 1], "entry", "0 = signal close, 1 = next open"),
    "buf":      Knob(0.0, [0.0], "stop", "anchor already includes the ATR stop"),
}
SIGNAL_KNOBS = ("pre", "stop_atr")


def raw_signals(df, ctx, k):
    if "earn_signal_dates" not in ctx:
        raise ValueError("EAP needs prepare_earnings(prep) (sweep.Prep calls it automatically)")
    c = df.close.to_numpy(float); a = np.asarray(ctx["atr"], float)
    sma = df.close.rolling(200).mean().to_numpy(float)
    e1 = df.index.get_indexer(pd.DatetimeIndex(ctx["earn_signal_dates"]))   # E-1 positions
    E = np.unique(e1[e1 >= 0]) + 1
    t = E - k["pre"] - 1
    t = t[(t >= 1) & (t < len(c))]
    t = t[np.isfinite(a[t]) & (a[t] > 0)]
    return pd.DataFrame(dict(t=t.astype(np.int64), side=1, anchor=c[t] - k["stop_atr"] * a[t], A=a[t], opp=np.nan,
                             trend200=np.nan_to_num(c[t] > sma[t], nan=False).astype(bool)))


def signals(raw, k):
    return raw[raw.trend200.to_numpy(bool)] if k["trend200"] else raw


def lines(df, ctx, k):
    return {}


def exit_recipe(k):
    n = k["pre"] + k["post"] + 1
    return dict(time_bars=n, max_hold=n + 5)
