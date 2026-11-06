"""ERG on s55 defaults: yesterday's ER/volatility and optional chop streak."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ta3.knobs import Knob, defaults
from ta3.strategies import s55 as BASE

KEY, NAME, SIDE = "ERG_S55", "Efficiency-ratio gate on S55 defaults", 1
TIMEFRAMES, EPISODE_GAP = ["D"], BASE.EPISODE_GAP
KNOBS = {
    "buf": Knob(0.1, [0.1], "stop", "Frozen base default buffer"),
    "mode": Knob(1, [0, 1], "entry", "Signal close / next open"),
    "er_len": Knob(10, [5, 10, 20], "signal", "Efficiency lookback"),
    "hi_cut": Knob(0.5, [0.4, 0.5, 0.6], "filter", "Skip when yesterday ER exceeds this"),
    "vol_cut": Knob(None, [None, 0.8, 0.9], "filter", "Yesterday RV20 percentile ceiling"),
    "chop_k": Knob(0, [0, 2, 3], "filter", "Prior consecutive ER days below 0.2"),
}
SIGNAL_KNOBS = ("er_len",)
LO_CUT, VOL_WINDOW = 0.2, 252

def _base():
    return defaults(BASE.KNOBS)

def raw_signals(df, ctx, k):
    b = _base()
    raw = BASE.signals(BASE.raw_signals(df, ctx, b), b).copy()
    c = df.close.astype(float)
    travel = c.diff().abs().rolling(k["er_len"]).sum()
    er = (c - c.shift(k["er_len"])).abs() / travel.where(travel > 0)
    # A flat, fully observed window has zero efficiency, rather than missing ER.
    er = er.mask(travel.eq(0), 0.0)
    rv = c.pct_change(fill_method=None).rolling(20).std(ddof=0)
    pct = rv.rolling(VOL_WINDOW).rank(pct=True)
    low = er.lt(LO_CUT)
    streak = low.astype(int).groupby((~low).cumsum()).cumsum()
    t = raw.t.to_numpy(np.int64)
    raw["er_prev"] = er.shift().to_numpy()[t]
    raw["vol_prev"] = pct.shift().to_numpy()[t]
    raw["chop_prev"] = streak.shift().to_numpy()[t]
    return raw

def signals(raw, k):
    m = raw.er_prev.notna() & raw.er_prev.le(k["hi_cut"])
    if k["vol_cut"] is not None:
        m &= raw.vol_prev.notna() & raw.vol_prev.le(k["vol_cut"])
    if k["chop_k"]:
        m &= raw.chop_prev.ge(k["chop_k"])
    return raw[m]

def lines(df, ctx, k):
    return BASE.lines(df, ctx, _base())

def exit_recipe(k):
    return BASE.exit_recipe(_base())
