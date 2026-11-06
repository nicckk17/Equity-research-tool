"""S55 EMA cross/stack. Defaults reproduce ta2's LIVE 9/21 cross survivor."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ta3.knobs import Knob

KEY = "S55"
NAME = "EMA cross / stack trend"
SIDE = 1
TIMEFRAMES = ["1h", "D", "W"]
EPISODE_GAP = 20
KNOBS = {
    "lengths": Knob((9, 21), [(7, 18), (9, 21), (12, 26), (20, 50), (50, 200), (9, 21, 55)], "signal", "EMA pair or rising stack"),
    "gap": Knob(20, [10, 15, 20, 25, 30], "signal", "minimum bars between raw episodes"),
    "anchor_bars": Knob(10, [5, 8, 10, 15, 20], "stop", "trailing low stop anchor"),
    "eff_bars": Knob(20, [10, 15, 20, 25, 30], "filter", "efficiency lookback"),
    "eff_min": Knob(0.25, [0.15, 0.2, 0.25, 0.3, 0.35], "filter", "minimum efficiency"),
    "clear": Knob(False, [False, True], "filter", "require efficiency gate"),
    "slope": Knob(False, [False, True], "filter", "require all EMAs rising"),
    "breakout": Knob(False, [False, True], "filter", "require range breakout"),
    "range_bars": Knob(20, [10, 15, 20, 25, 30], "filter", "prior range lookback"),
    "buf": Knob(0.1, [0.05, 0.1, 0.3, 0.5], "stop", "stop buffer in ATR"),
    "exit": Knob("ema", ["ema", "reverse_cross", "2R", "trail3atr"], "exit", "exit rule"),
    "exit_ema": Knob(21, [9, 13, 21, 34, 50], "exit", "EMA close-break period"),
    "target_R": Knob(2.0, [1.5, 2.0, 2.5, 3.0], "exit", "fixed profit target in R"),
    "trail_atr": Knob(3.0, [2.0, 2.5, 3.0, 3.5], "exit", "chandelier ATR multiple"),
    "max_hold": Knob(60, [40, 50, 60, 80], "exit", "hard holding limit"),
    "mode": Knob(1, [0, 1], "entry", "signal close or next open"),
}
# Include every knob read by raw_signals OR lines: sweep caches both together.
SIGNAL_KNOBS = ("lengths", "gap", "anchor_bars", "eff_bars", "eff_min", "range_bars", "exit_ema")


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



def _regime(emas, lengths):
    ready = np.ones(len(next(iter(emas.values()))), dtype=bool)
    up, down = ready.copy(), ready.copy()
    for k in lengths:
        ready &= emas[k].notna().to_numpy()
    for f, s in zip(lengths[:-1], lengths[1:]):
        up &= (emas[f] > emas[s]).to_numpy()
        down &= (emas[f] < emas[s]).to_numpy()
    if len(lengths) == 3:
        for k in lengths:
            up &= (emas[k].diff() > 0).to_numpy()
            down &= (emas[k].diff() < 0).to_numpy()
        ready &= emas[lengths[-1]].shift().notna().to_numpy()
    return np.where(up & ready, 1, np.where(down & ready, -1, 0)), ready



def raw_signals(df, ctx, k):
    columns = ["t", "side", "anchor", "A", "opp", "clear", "slope", "breakout"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    bars, a, pos = _clean(df, ctx)
    c = bars.close.astype(float)
    lengths = k["lengths"]
    emas = {n: c.ewm(span=n, adjust=False, min_periods=n).mean() for n in lengths}
    floor, ceiling = bars.low.rolling(k["anchor_bars"]).min(), bars.high.rolling(k["anchor_bars"]).max()
    travel = c.diff().abs().rolling(k["eff_bars"]).sum()
    efficiency = (c - c.shift(k["eff_bars"])).abs() / travel.where(travel > 0)
    upper = bars.high.rolling(k["range_bars"]).max().shift()
    lower = bars.low.rolling(k["range_bars"]).min().shift()
    regime, ready = _regime(emas, lengths)
    previous, initialized, last = 0, False, -k["gap"]
    rows = []
    for t, side in enumerate(regime):
        if not ready[t]:
            continue
        if not initialized:
            previous, initialized = side, True
            continue
        old = previous
        if side or len(lengths) == 3:
            previous = side
        if side == 0 or side == old:
            continue
        if t - last < k["gap"]:
            continue
        last = t  # Both directions consume episodes before long-only selection.
        anchor = floor.iloc[t] if side == 1 else ceiling.iloc[t]
        if not np.isfinite(a[t]) or a[t] <= 0 or not np.isfinite(anchor):
            continue
        slope = all(side * (emas[n].iloc[t] - emas[n].iloc[t-1]) > 0 for n in lengths)
        rows.append(dict(t=int(pos[t]), side=int(side), anchor=float(anchor), A=a[t], opp=np.nan,
                         clear=bool(efficiency.iloc[t] >= k["eff_min"]), slope=bool(slope),
                         breakout=bool(c.iloc[t] > upper.iloc[t] if side == 1 else c.iloc[t] < lower.iloc[t])))
    return pd.DataFrame(rows, columns=columns).sort_values(["t", "side"], kind="stable", ignore_index=True)


def signals(raw, k):
    m = raw.side.eq(SIDE).to_numpy()
    for flag in ("clear", "slope", "breakout"):
        if k[flag]:
            m &= raw[flag].to_numpy(bool)
    return raw[m]


def lines(df, ctx, k):
    # ta2 intentionally computes exit lines on uncleaned df, unlike raw signals.
    c = df.close.astype(float)
    e = {n: c.ewm(span=n, adjust=False, min_periods=n).mean() for n in set(k["lengths"]) | {k["exit_ema"]}}
    return {"ema": (c - e[k["exit_ema"]]).to_numpy(float),
            "reverse": (e[k["lengths"][0]] - e[k["lengths"][1]]).to_numpy(float)}


def exit_recipe(k):
    if k["exit"] in ("ema", "reverse_cross"):
        return dict(state="ema" if k["exit"] == "ema" else "reverse", max_hold=k["max_hold"])
    if k["exit"] == "2R":
        return dict(target_R=k["target_R"], max_hold=k["max_hold"])
    return dict(trail_atr=k["trail_atr"], max_hold=k["max_hold"])
