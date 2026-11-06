"""S55 EMA cross / stack trend. TIER: STRONG (only strategy that passed the US cold test cleanly). Signal code from v1."""

from __future__ import annotations

import time
import numpy as np
import pandas as pd
from numba import njit

OUT = "S55"
CHUNK = 5
SIDES = (1, -1)
MODES = [0, 1]
BUFS = [0.1, 0.5]
FLAGS = ["all", "clear", "slope", "range20"]
SETS = {"cross9_21": (9, 21), "stack9_21_55": (9, 21, 55),
        "cross20_50": (20, 50), "cross50_200": (50, 200)}
EPISODE_GAP = 20


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


def _emas(c):
    return {k: c.ewm(span=k, adjust=False, min_periods=k).mean()
            for k in (9, 20, 21, 50, 55, 200)}


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


def signals(df, ctx):
    columns = ["t", "side", "anchor", "A", "opp", "fam"] + FLAGS
    if df.empty:
        return pd.DataFrame(columns=columns)
    bars, a, pos = _clean(df, ctx)
    c = bars.close.astype(float)
    emas = _emas(c)
    floor, ceiling = bars.low.rolling(10).min(), bars.high.rolling(10).max()
    travel = c.diff().abs().rolling(20).sum()
    efficiency = (c - c.shift(20)).abs() / travel.where(travel > 0)
    upper, lower = bars.high.rolling(20).max().shift(), bars.low.rolling(20).min().shift()
    rows = []
    for fam, lengths in SETS.items():
        regime, ready = _regime(emas, lengths)
        previous, initialized, last = 0, False, -EPISODE_GAP
        for t, side in enumerate(regime):
            if not ready[t]:
                continue
            if not initialized:
                previous, initialized = side, True
                continue  # Initial history does not establish a cross.
            old = previous
            # For pairs equality retains the last side. A mixed/flat stack
            # ends its episode; a new complete stack starts a new episode.
            if side or len(lengths) == 3:
                previous = side
            if side == 0 or side == old:
                continue
            if t - last < EPISODE_GAP:
                continue  # Raw transition is consumed, never delayed.
            last = t
            anchor = floor.iloc[t] if side == 1 else ceiling.iloc[t]
            if not np.isfinite(a[t]) or a[t] <= 0 or not np.isfinite(anchor):
                continue
            slope = all(side * (emas[k].iloc[t] - emas[k].iloc[t-1]) > 0 for k in lengths)
            rows.append(dict(t=int(pos[t]), side=int(side), anchor=float(anchor), A=a[t],
                             opp=np.nan, fam=fam, all=True, clear=bool(efficiency.iloc[t] >= 0.25),
                             slope=bool(slope), range20=bool(c.iloc[t] > upper.iloc[t] if side == 1
                                                          else c.iloc[t] < lower.iloc[t])))
    result = pd.DataFrame(rows, columns=columns)
    result[FLAGS] = result[FLAGS].astype(bool)
    return result.sort_values(["t", "side", "fam"], kind="stable", ignore_index=True)


def specs():
    return [(dict(ma_set=fam, gate=gate), fam, flags)
            for fam in SETS
            for gate, flags in (("none", ()), ("clear", ("clear",)),
                                ("slope", ("slope",)), ("clear+slope", ("clear", "slope")))]


NAMED = {
    "as taught (daily 9/21/55 rising stack, exit EMA9)": dict(
        fam="stack9_21_55", flags=(), target="ema9", mode=1, buf=0.1),
    "as traded (daily 9/21 cross, exit EMA21)": dict(
        fam="cross9_21", flags=(), target="ema21", mode=1, buf=0.1),
    "50/200 cross (daily, exit EMA50)": dict(
        fam="cross50_200", flags=(), target="ema50", mode=1, buf=0.1),
}
LADDER = dict(base=dict(NAMED["as taught (daily 9/21/55 rising stack, exit EMA9)"]), steps=[
    ("base daily rising stack", {}, True),
    ("+ skip chop: 20-bar efficiency >= 0.25", {"add": "clear"}, True),
    ("exit EMA21", {"target": "ema21"}, False),
    ("exit EMA50", {"target": "ema50"}, False),
    ("20-bar range breakout proxy", {"add": "range20"}, False),
])


# ------------------------------------------------------------ v2 adapter
TIER = "strong"
EVIDENCE = ("as traded (9/21 cross, exit EMA21) beats random twins in all 4 windows: TSX IS +11 (p .002), OOS +15 (.001), "
            "US IS +17 (.000), US OOS +26 (.000) R/yr. Small per trade (+0.02..0.10R).")
EXITS = {"ema9": dict(state="ema9", max_hold=60), "ema21": dict(state="ema21", max_hold=60),
         "ema50": dict(state="ema50", max_hold=60), "reverse_cross": dict(state="reverse", max_hold=60)}
TARGETS = list(EXITS)


def lines(df, ctx, fam, side):
    c = df.close.astype(float); e = _emas(c); L = SETS[fam]
    out = {f"ema{k}": (c - e[k]).to_numpy(float) for k in (9, 21, 50)}
    out["reverse"] = (e[L[0]] - e[L[1]]).to_numpy(float)
    return out


KEEP = {
    "as traded: daily 9/21 EMA cross, exit EMA21": dict(fam="cross9_21", flags=(), target="ema21", mode=1, buf=0.1, sides=(1,)),
    "IS pick 3: 9/21 cross, exit EMA9": dict(fam="cross9_21", flags=(), target="ema9", mode=1, buf=0.5, sides=(1,)),
}
LIVE = "as traded: daily 9/21 EMA cross, exit EMA21"
