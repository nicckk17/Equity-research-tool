"""S56 first directional EMA retest. Defaults reproduce ta2's LIVE EMA34/8 survivor."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ta3.knobs import Knob

KEY = "S56"
NAME = "EMA break and retest"
SIDE = 1
TIMEFRAMES = ["1h", "D", "W"]
EPISODE_GAP = 10
KNOBS = {
    "main": Knob(34, [21, 28, 34, 50, 55], "signal", "cross/retest EMA"),
    "trail": Knob(8, [5, 8, 10, 13, 20], "exit", "exit EMA"),
    "retest_bars": Knob(20, [10, 15, 20, 25, 30], "signal", "cross setup expiry"),
    "raw_tol": Knob(0.02, [0.01, 0.015, 0.02, 0.025, 0.03], "signal", "raw retest zone before gates"),
    "gap": Knob(10, [5, 8, 10, 15, 20], "signal", "raw episode gap"),
    "tol": Knob(0.02, [0.005, 0.01, 0.015, 0.02, 0.025], "filter", "optional tighter retest tolerance"),
    "strong": Knob(True, [False, True], "filter", "require strong candle"),
    "body_min": Knob(0.6, [0.4, 0.5, 0.6, 0.7, 0.8], "filter", "minimum body / range"),
    "slope": Knob(False, [False, True], "filter", "require favorable main EMA slope"),
    "buf": Knob(0.5, [0.1, 0.3, 0.5, 0.8, 1.0], "stop", "stop buffer in ATR"),
    "exit": Knob("ema_trail", ["ema_trail", "ema_main", "pivot", "2R"], "exit", "exit rule"),
    "target_R": Knob(2.0, [1.5, 2.0, 2.5, 3.0], "exit", "fixed profit target in R"),
    "pivot_span": Knob(1.0, [0.618, 0.786, 1.0, 1.272], "exit", "previous-month pivot range multiple"),
    "max_hold": Knob(120, [60, 90, 120, 150], "exit", "hard holding limit"),
    "mode": Knob(1, [0, 1], "entry", "signal close or next open"),
}
SIGNAL_KNOBS = ("main", "trail", "retest_bars", "raw_tol", "gap", "body_min", "pivot_span")


def _clean(df, ctx):
    if not isinstance(df.index, pd.DatetimeIndex) or not df.index.is_unique or not df.index.is_monotonic_increasing:
        raise ValueError("df requires a unique increasing DatetimeIndex")
    a = np.asarray(ctx["atr"], dtype=float)
    if a.ndim != 1 or len(a) != len(df):
        raise ValueError("ctx['atr'] must align with df")
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    good = (np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c)
            & (h >= np.maximum(o, c)) & (l <= np.minimum(o, c)))
    pos = np.flatnonzero(good)
    return df.iloc[pos], a[pos], pos



def _pivots(bars, multiple):
    """Monthly Fibonacci R3/S3 from the previous calendar month only."""
    months = bars.index.to_period("M")
    monthly = bars.groupby(months).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    previous = monthly.reindex(months - 1)
    p = (previous.high + previous.low + previous.close).to_numpy(dtype=float) / 3
    span = (previous.high - previous.low).to_numpy(dtype=float)
    return p + multiple * span, p - multiple * span



def raw_signals(df, ctx, k):
    columns = ["t", "side", "anchor", "A", "opp", "distance", "strong", "slope"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    bars, a, pos = _clean(df, ctx)
    o, h, l, c = (bars[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    ma = bars.close.astype(float).ewm(span=k["main"], adjust=False, min_periods=k["main"]).mean().to_numpy()
    active, start, previous, last = 0, -1, 0, -k["gap"]
    rows = []
    for t in range(len(bars)):
        if not np.isfinite(ma[t]):
            continue
        side = 1 if c[t] > ma[t] else -1 if c[t] < ma[t] else 0
        cross = side != 0 and previous != 0 and side != previous
        if cross:
            active, start = side, t
        elif active:
            if t - start > k["retest_bars"] or active * (c[t] - ma[t]) < 0:
                active = 0
            elif t > start:
                extreme = l[t] if active == 1 else h[t]
                distance = max(0.0, active * (extreme - ma[t])) / max(abs(ma[t]), 1e-12)
                if distance <= k["raw_tol"] and active * (c[t] - o[t]) > 0:
                    sd = active
                    active = 0  # Consume before tolerance, strong/slope, and ATR gates.
                    if t - last >= k["gap"]:
                        last = t
                        if np.isfinite(a[t]) and a[t] > 0:
                            span = h[t] - l[t]
                            rows.append(dict(t=int(pos[t]), side=sd, anchor=float(extreme), A=float(a[t]),
                                opp=np.nan, distance=distance,
                                strong=bool(span > 0 and abs(c[t]-o[t]) >= k["body_min"]*span),
                                slope=bool(sd*(ma[t]-ma[t-1]) > 0)))
        if side:
            previous = side
    return pd.DataFrame(rows, columns=columns).sort_values(["t", "side"], kind="stable", ignore_index=True)


def signals(raw, k):
    m = raw.side.eq(SIDE).to_numpy() & (raw.distance.to_numpy(float) <= k["tol"])
    for flag in ("strong", "slope"):
        if k[flag]:
            m &= raw[flag].to_numpy(bool)
    return raw[m]


def lines(df, ctx, k):
    c = df.close.astype(float)
    ph, pl = _pivots(df, k["pivot_span"])
    return {"ema_trail": (c - c.ewm(span=k["trail"], adjust=False, min_periods=k["trail"]).mean()).to_numpy(float),
            "ema_main": (c - c.ewm(span=k["main"], adjust=False, min_periods=k["main"]).mean()).to_numpy(float),
            "piv_hi": ph, "piv_lo": pl}


def exit_recipe(k):
    e = k["exit"]
    if e == "2R":
        return dict(target_R=k["target_R"], max_hold=k["max_hold"])
    if e == "pivot":
        return dict(target=("piv_hi", "piv_lo"), max_hold=k["max_hold"])
    return dict(state=e, max_hold=k["max_hold"])
