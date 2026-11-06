"""BB200: Bollinger dip in an optional 200-SMA uptrend."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ta3.knobs import Knob
from ta2.strategies.common import EXIT_PANEL

KEY, NAME, SIDE = "BB200", "Bollinger dip above 200 SMA", 1
TIMEFRAMES, EPISODE_GAP = ["1h", "D"], 1
KNOBS = {
    "bb_len": Knob(20, [10, 15, 20, 30], "signal", "Bollinger length"),
    "bb_k": Knob(2.0, [1.5, 2.0, 2.5], "signal", "Population standard deviations"),
    "trend200": Knob(True, [False, True], "filter", "Close above 200 SMA"),
    "buf": Knob(0.5, [0.1, 0.5, 1.0], "stop", "10-bar low minus buffer ATR"),
    "exit": Knob("time10", ["time5", "time10", "2R", "trail2atr", "middle"], "exit", "Exit recipe"),
    "mode": Knob(1, [0, 1], "entry", "Signal close / next open"),
}
SIGNAL_KNOBS = ("bb_len", "bb_k")

def raw_signals(df, ctx, k):
    c = df.close.astype(float)
    mid = c.rolling(k["bb_len"]).mean()
    lower = mid - k["bb_k"] * c.rolling(k["bb_len"]).std(ddof=0)
    floor = df.low.rolling(10).min().to_numpy(float)
    a = np.asarray(ctx["atr"], float)
    t = np.flatnonzero((c < lower).to_numpy() & np.isfinite(floor) & np.isfinite(a) & (a > 0))
    return pd.DataFrame(dict(t=t, side=1, anchor=floor[t], A=a[t], opp=np.nan,
                             trend200=(c > c.rolling(200).mean()).to_numpy()[t]))

def signals(raw, k):
    return raw[raw.trend200] if k["trend200"] else raw

def lines(df, ctx, k):
    c = df.close.astype(float)
    # Engine long close_line exits when c < line: reflection expresses c > middle.
    return {"above_middle": (2 * c - c.rolling(k["bb_len"]).mean()).to_numpy(float)}

def exit_recipe(k):
    if k["exit"] == "middle":
        return dict(close_line="above_middle", max_hold=60)
    return dict(EXIT_PANEL[k["exit"]])
