"""ATHD: close above prior long Donchian high, with a wide ATR trail."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ta3.knobs import Knob

KEY, NAME, SIDE = "ATHD", "Long Donchian / observed-history ATH breakout", 1
TIMEFRAMES, EPISODE_GAP = ["D"], 1
KNOBS = {
    "lookback": Knob(252, [100, 200, 252, "ATH"], "signal", "Prior high lookback"),
    "k": Knob(5.0, [3.0, 5.0, 8.0], "stop", "Initial stop and trail in signal ATR"),
    "mode": Knob(1, [0, 1], "entry", "Signal close / next open"),
    "buf": Knob(0.0, [0.0], "stop", "Anchor includes ATR distance"),
}
SIGNAL_KNOBS = ("lookback", "k")

def raw_signals(df, ctx, k):
    high = df.high.expanding(min_periods=252).max() if k["lookback"] == "ATH" else df.high.rolling(k["lookback"]).max()
    a = np.asarray(ctx["atr"], float)
    t = np.flatnonzero(df.close.gt(high.shift()).to_numpy() & np.isfinite(a) & (a > 0))
    return pd.DataFrame(dict(t=t, side=1, anchor=df.close.to_numpy()[t] - k["k"] * a[t], A=a[t], opp=np.nan))

def signals(raw, k):
    return raw

def lines(df, ctx, k):
    return {}

def exit_recipe(k):
    return dict(trail_atr=k["k"], max_hold=252)
