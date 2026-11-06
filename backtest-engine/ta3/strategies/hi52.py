"""HI52: first visit to the vicinity of a trailing 252-bar high."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ta3.knobs import Knob

KEY, NAME, SIDE = "HI52", "52-week-high nearness", 1
TIMEFRAMES, EPISODE_GAP = ["D"], 20
KNOBS = {
    "near": Knob(0.05, [0.02, 0.05, 0.10], "signal", "Distance below 252-bar high"),
    "trend200": Knob(True, [False, True], "filter", "Close above 200 SMA"),
    "stop_atr": Knob(3.0, [3.0, 5.0, 8.0], "stop", "Initial signal-close ATR stop"),
    "exit": Knob("trail5", ["trail3", "trail5", "trail8", "time63", "time126"], "exit", "ATR trail or time exit"),
    "mode": Knob(1, [0, 1], "entry", "Signal close / next open"),
    "buf": Knob(0.0, [0.0], "stop", "Anchor already includes ATR distance"),
}
SIGNAL_KNOBS = ("near", "stop_atr")

def raw_signals(df, ctx, k):
    c = df.close.astype(float)
    near = c.ge((1 - k["near"]) * df.high.rolling(252).max())
    # A visit requires the preceding GAP bars to contain no visit; no periodic re-entry.
    first = near & near.shift().rolling(EPISODE_GAP, min_periods=EPISODE_GAP).sum().eq(0)
    a = np.asarray(ctx["atr"], float)
    t = np.flatnonzero(first.to_numpy() & np.isfinite(a) & (a > 0))
    return pd.DataFrame(dict(t=t, side=1, anchor=c.to_numpy()[t] - k["stop_atr"] * a[t],
                             A=a[t], opp=np.nan, trend200=c.gt(c.rolling(200).mean()).to_numpy()[t]))

def signals(raw, k):
    return raw[raw.trend200] if k["trend200"] else raw

def lines(df, ctx, k):
    return {}

def exit_recipe(k):
    e = k["exit"]
    if e.startswith("trail"):
        return dict(trail_atr=float(e[5:]), max_hold=252)
    return dict(time_bars=int(e[4:]), max_hold=253)
