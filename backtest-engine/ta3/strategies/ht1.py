"""HT1 kept parabolic limit entry. Uses prior-bar setup and ATR, current open/fill only."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ta3.knobs import Knob
from ta2.strategies.ht_common import index_bars

KEY = "HT1"
NAME = "Parabolic dip limit at prior low"
SIDE = 1
TIMEFRAMES = ["D"]  # The kept setup and index helper use daily bars.
EPISODE_GAP = 0     # ta2 has no episode debounce for HT1.
KNOBS = {
    "limit_lag": Knob(1, [1, 2, 3], "entry", "bars back for limit-price low"),
    "up_bars": Knob(6, [4, 5, 6, 7, 8], "signal", "up-close count window"),
    "up_min": Knob(5, [3, 4, 5, 6], "signal", "minimum up closes"),
    "run_bars": Knob(10, [5, 8, 10, 12, 15], "signal", "alternative run lookback"),
    "run_min": Knob(0.15, [0.1, 0.125, 0.15, 0.175, 0.2], "signal", "alternative minimum run return"),
    "target_bars": Knob(6, [3, 5, 6, 8, 10], "exit", "prior run-high lookback"),
    "warmup": Knob(201, [151, 181, 201, 221, 251], "signal", "first eligible signal bar"),
    "trend_bars": Knob(200, [150, 175, 200, 225, 250], "filter", "optional trend SMA"),
    "idx_up": Knob(True, [False, True], "filter", "index opens flat/up"),
    "trend": Knob(False, [False, True], "filter", "prior close above trend SMA"),
    "streak": Knob(False, [False, True], "filter", "require up-close count arm"),
    "big": Knob(False, [False, True], "filter", "require return arm"),
    "buf": Knob(1.0, [0.5, 0.75, 1.0, 1.25, 1.5], "stop", "order-price stop buffer in prior ATR"),
    "exit": Knob("opp", ["opp", "day", "next", "time3", "2R"], "exit", "exit rule"),
    "max_hold": Knob(5, [3, 5, 7, 10], "exit", "hard holding limit"),
    "next_bars": Knob(1, [1, 2, 3], "exit", "short hold exit bars"),
    "time_bars": Knob(3, [2, 3, 4, 5], "exit", "timed exit bars"),
    "target_R": Knob(2.0, [1.5, 2.0, 2.5, 3.0], "exit", "fixed profit target in R"),
    "mode": Knob(3, [0, 1, 3], "entry", "close, next open, or original limit fill"),
}
SIGNAL_KNOBS = ("up_bars", "up_min", "run_bars", "run_min", "target_bars", "warmup", "trend_bars", "limit_lag")


def raw_signals(df, ctx, k):
    columns = ["t", "side", "anchor", "A", "opp", "px", "idx_up", "trend", "streak", "big"]
    o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    a = np.asarray(ctx["atr"], float)
    sma = (np.asarray(ctx["sma"][200], float) if k["trend_bars"] == 200
           else df.close.rolling(k["trend_bars"]).mean().to_numpy(float))
    ix = index_bars(df, ctx)
    rows = []
    start = max(k["warmup"], k["up_bars"] + 1, k["run_bars"] + 1, k["target_bars"], k["limit_lag"])
    for t in range(start, len(df)):
        p = t - 1
        if not (np.isfinite(a[p]) and a[p] > 0):
            continue
        ups = int(np.sum(np.diff(c[p-k["up_bars"]:p+1]) > 0))
        run = c[p] / c[p-k["run_bars"]] - 1
        if (ups >= k["up_min"] or run >= k["run_min"]) and l[t] <= l[t-k["limit_lag"]]:
            px = min(o[t], l[t-k["limit_lag"]])
            rows.append(dict(t=t, side=SIDE, anchor=px, A=a[p], px=px,
                opp=float(np.max(h[p-k["target_bars"]+1:p+1])),
                idx_up=bool(np.isfinite(ix["c"][p]) and ix["o"][t] >= ix["c"][p]),
                trend=bool(c[p] > sma[p]), streak=ups >= k["up_min"], big=run >= k["run_min"]))
    return pd.DataFrame(rows, columns=columns)


def signals(raw, k):
    m = np.ones(len(raw), bool)
    for flag in ("idx_up", "trend", "streak", "big"):
        if k[flag]:
            m &= raw[flag].to_numpy(bool)
    return raw[m]


def lines(df, ctx, k):
    return {}


def exit_recipe(k):
    e = k["exit"]
    if e == "opp":
        return dict(target="opp", max_hold=k["max_hold"])
    if e == "day":
        return dict(same_day=True, max_hold=k["max_hold"])
    if e in ("next", "time3"):
        return dict(time_bars=k["next_bars"] if e == "next" else k["time_bars"], max_hold=k["max_hold"])
    return dict(target_R=k["target_R"], max_hold=k["max_hold"])
