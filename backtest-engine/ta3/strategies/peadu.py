"""PEADU: post-earnings drift after a big UP earnings move (long only). Claude, 2026-11-05.
Signal at t = E+1 (reaction known at that close). Stop = entry-ish close - stop_atr x ATR(t)."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ..knobs import Knob
from ._pead_common import events, exit_recipe, lines, prepare_earnings, attach_earnings  # noqa: F401

KEY, NAME, SIDE = "PEADU", "Post-earnings drift (up moves)", 1
TIMEFRAMES, EPISODE_GAP = ["D"], 1
KNOBS = {
    "min_atr":  Knob(2, [1, 2, 3], "signal", "min earnings move in ATR units"),
    "trend200": Knob(False, [False, True], "filter", "close above 200 SMA"),
    "stop_atr": Knob(3, [2, 3, 5], "stop", "stop = close(t) - k x ATR"),
    "exit":     Knob("time40", ["time20", "time40", "time60", "trail3atr"], "exit", "exit rule"),
    "mode":     Knob(1, [0, 1], "entry", "0 = close of E+1, 1 = next open"),
    "buf":      Knob(0.0, [0.0], "stop", "anchor already includes the ATR stop"),
}
SIGNAL_KNOBS = ("min_atr", "stop_atr")


def raw_signals(df, ctx, k):
    E, r2, size = events(df, ctx)
    c = df.close.to_numpy(float); a = np.asarray(ctx["atr"], float)
    sma = df.close.rolling(200).mean().to_numpy(float)
    m = (r2 > 0) & (size >= k["min_atr"])
    t = E[m] + 1
    t = t[np.isfinite(a[t]) & (a[t] > 0)]
    return pd.DataFrame(dict(t=t.astype(np.int64), side=1, anchor=c[t] - k["stop_atr"] * a[t], A=a[t], opp=np.nan,
                             trend200=np.nan_to_num(c[t] > sma[t], nan=False).astype(bool)))


def signals(raw, k):
    return raw[raw.trend200.to_numpy(bool)] if k["trend200"] else raw
