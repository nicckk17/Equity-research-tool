"""DENS: equal votes from four Donchian lookbacks."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ta3.knobs import Knob

KEY, NAME, SIDE = "DENS", "Donchian ensemble", 1
TIMEFRAMES, EPISODE_GAP = ["D"], 1
LOOKBACKS = (20, 55, 100, 200)
KNOBS = {
    "vote_type": Knob("breakout", ["breakout", "above_mid"], "signal", "Prior channel high or midpoint"),
    "v": Knob(2, [2, 3, 4], "signal", "Entry vote threshold"),
    "exit": Knob("trail5", ["trail3", "trail5", "vote"], "exit", "ATR trail or vote exit"),
    "v_exit": Knob(1, [1, 2], "exit", "Exit when vote strictly below threshold"),
    "mode": Knob(1, [0, 1], "entry", "Signal close / next open"),
    "buf": Knob(0.0, [0.0], "stop", "Initial stop fixed at three signal ATR"),
}
SIGNAL_KNOBS = ("vote_type", "v", "v_exit")

def _votes(df, k):
    count = pd.Series(0, index=df.index, dtype=int)
    ready = pd.Series(True, index=df.index)
    for n in LOOKBACKS:
        high = df.high.rolling(n).max().shift()
        threshold = high if k["vote_type"] == "breakout" else (high + df.low.rolling(n).min().shift()) / 2
        ready &= threshold.notna()
        count += df.close.gt(threshold).astype(int)
    return count.where(ready)

def raw_signals(df, ctx, k):
    vote = _votes(df, k)
    up = vote.ge(k["v"]) & vote.shift().lt(k["v"])
    a = np.asarray(ctx["atr"], float)
    t = np.flatnonzero(up.to_numpy() & np.isfinite(a) & (a > 0))
    return pd.DataFrame(dict(t=t, side=1, anchor=df.close.to_numpy()[t] - 3 * a[t], A=a[t], opp=np.nan))

def signals(raw, k):
    return raw

def lines(df, ctx, k):
    # Half offset makes equality non-exiting under the engine's strict negative state test.
    return {"vote": (_votes(df, k) - k["v_exit"] + 0.5).to_numpy(float)}

def exit_recipe(k):
    if k["exit"] == "vote":
        return dict(state="vote", max_hold=252)
    return dict(trail_atr=float(k["exit"][5:]), max_hold=252)
