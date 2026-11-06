"""S53 MACD histogram cross, knob version (ta3). Same signal rule as ta2/strategies/s53_macd.py; every moving
part is a knob. Defaults = the live "survivor" (12/26/9, below zero line, opposite-cross exit, next open, 0.5 ATR)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..knobs import Knob
from ta2.strategies.common import EXIT_PANEL

KEY = "S53"
NAME = "MACD histogram cross"
SIDE = 1                                    # long only (shorts lost in v1)
TIMEFRAMES = ["1h", "D", "W"]
EPISODE_GAP = 5

KNOBS = {
    "fast":   Knob(12, [8, 10, 12, 14, 16], "signal", "MACD fast EMA"),
    "slow":   Knob(26, [20, 23, 26, 29, 32], "signal", "MACD slow EMA"),
    "signal": Knob(9, [5, 7, 9, 11, 13], "signal", "MACD signal EMA"),
    "zero":   Knob(True, [False, True], "filter", "buy only below the zero line"),
    "weekly": Knob(False, [False, True], "filter", "weekly MACD rising"),
    "buf":    Knob(0.5, [0.1, 0.3, 0.5, 0.8], "stop", "stop = 10-bar low - buf x ATR"),
    "exit":   Knob("opposite_cross", ["opposite_cross", "hist_turn", "2R", "trail3atr", "time10"], "exit", "exit rule"),
    "mode":   Knob(1, [0, 1], "entry", "0 = signal close, 1 = next open"),
}
SIGNAL_KNOBS = ("fast", "slow", "signal")    # knobs that change the raw signal list (cached on these)


def _macd(c, f, s, g):
    line = c.ewm(span=f, adjust=False, min_periods=f).mean() - c.ewm(span=s, adjust=False, min_periods=s).mean()
    return line, line - line.ewm(span=g, adjust=False, min_periods=g).mean()


def raw_signals(df, ctx, k):
    """All long histogram up-crosses (one per EPISODE_GAP bars) with filter columns; filters applied later."""
    if k["fast"] >= k["slow"]:
        return pd.DataFrame(columns=["t", "side", "anchor", "A", "opp", "zero", "weekly"])
    c = df.close.astype(float)
    line, hist = _macd(c, k["fast"], k["slow"], k["signal"])
    wk = c.resample("W-FRI", closed="right", label="right").last().dropna()
    wline, _ = _macd(wk, k["fast"], k["slow"], k["signal"])
    wdir = wline.diff().reindex(c.index, method="ffill")
    up = ((hist > 0) & (hist.shift() <= 0)).to_numpy()
    down = ((hist < 0) & (hist.shift() >= 0)).to_numpy()
    floor = df.low.rolling(10).min().to_numpy(); a = np.asarray(ctx["atr"], float)
    keep = []; last = -EPISODE_GAP
    for t in np.flatnonzero(up | down):          # episodes counted over both crosses, as v1/v2
        if t - last >= EPISODE_GAP:
            last = t
            if up[t] and np.isfinite(a[t]) and a[t] > 0 and np.isfinite(floor[t]):
                keep.append(t)
    t = np.array(keep, dtype=np.int64)
    return pd.DataFrame(dict(t=t, side=1, anchor=floor[t], A=a[t], opp=np.nan,
                             zero=line.to_numpy()[t] < 0, weekly=wdir.to_numpy()[t] > 0))


def signals(raw, k):
    m = np.ones(len(raw), bool)
    if k["zero"]:
        m &= raw.zero.to_numpy(bool)
    if k["weekly"]:
        m &= raw.weekly.to_numpy(bool)
    return raw[m]


def lines(df, ctx, k):
    _, hist = _macd(df.close.astype(float), k["fast"], k["slow"], k["signal"])
    return {"hist": hist.to_numpy(float), "hist_diff": hist.diff().to_numpy(float)}


def exit_recipe(k):
    e = k["exit"]
    if e == "opposite_cross":
        return dict(state="hist", max_hold=60)
    if e == "hist_turn":
        return dict(state="hist_diff", max_hold=60)
    return dict(EXIT_PANEL[e])
