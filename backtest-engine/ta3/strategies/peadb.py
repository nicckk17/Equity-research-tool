"""PEADB: bounce after a big DOWN earnings move (long only). Claude, 2026-11-05.
Event: R2 < 0 and size >= min_atr. Signal at t = E+1+wait. Stop = lowest low from E to t - buf x ATR(t)."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ..knobs import Knob
from ._pead_common import events, exit_recipe, lines, prepare_earnings, attach_earnings  # noqa: F401

KEY, NAME, SIDE = "PEADB", "Post-earnings bounce (after big drops)", 1
TIMEFRAMES, EPISODE_GAP = ["D"], 1
KNOBS = {
    "min_atr": Knob(2, [1, 2, 3], "signal", "min earnings drop in ATR units"),
    "wait":    Knob(5, [3, 5, 10], "signal", "bars to wait after E+1"),
    "confirm": Knob("none", ["none", "up_day"], "filter", "require an up close on the signal bar"),
    "buf":     Knob(1.0, [0.5, 1.0, 2.0], "stop", "stop = lowest low since E - buf x ATR"),
    "exit":    Knob("time40", ["time20", "time40", "time60", "trail3atr"], "exit", "exit rule"),
    "mode":    Knob(1, [0, 1], "entry", "0 = signal close, 1 = next open"),
}
SIGNAL_KNOBS = ("min_atr", "wait")


def raw_signals(df, ctx, k):
    E, r2, size = events(df, ctx)
    c = df.close.to_numpy(float); lo = df.low.to_numpy(float); a = np.asarray(ctx["atr"], float)
    m = (r2 < 0) & (size >= k["min_atr"])
    E = E[m]; t = E + 1 + k["wait"]
    ok = t < len(c); E, t = E[ok], t[ok]
    ok = np.isfinite(a[t]) & (a[t] > 0); E, t = E[ok], t[ok]
    floor = np.array([lo[e:ti + 1].min() for e, ti in zip(E, t)], float)
    up = c[t] > c[t - 1]
    return pd.DataFrame(dict(t=t.astype(np.int64), side=1, anchor=floor, A=a[t], opp=np.nan, up_day=up))


def signals(raw, k):
    return raw[raw.up_day.to_numpy(bool)] if k["confirm"] == "up_day" else raw
