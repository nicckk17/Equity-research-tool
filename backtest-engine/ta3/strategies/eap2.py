"""EAP2: earnings announcement premium, improved (Claude, 2026-11-05).
Changes vs EAP: longer run-up options (pre up to 25 sessions) and the Frazzini & Lamont "volume concentration" filter:
for each event, conc = average over the stock's PREVIOUS 4 earnings events of
    mean volume(E-1..E+1) / mean volume(E-61..E-2)
(only events whose E+1 is before the signal bar are used -> no look-ahead). Trade only if conc >= vconc."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ..knobs import Knob
from .earn import attach_earnings, prepare_earnings  # noqa: F401

KEY, NAME, SIDE = "EAP2", "Earnings announcement premium + volume-concentration filter", 1
TIMEFRAMES, EPISODE_GAP = ["D"], 1
KNOBS = {
    "pre":      Knob(15, [10, 15, 20, 25], "signal", "sessions before E to enter"),
    "post":     Knob(2, [0, 2, 5], "exit", "sessions after E to exit"),
    "vconc":    Knob(0.0, [0.0, 1.2, 1.4, 1.6], "filter", "min past earnings-volume concentration (0 = off)"),
    "stop_atr": Knob(5, [3, 5], "stop", "stop = close(t) - k x ATR"),
    "mode":     Knob(1, [0, 1], "entry", "0 = signal close, 1 = next open"),
    "buf":      Knob(0.0, [0.0], "stop", "anchor already includes the ATR stop"),
}
SIGNAL_KNOBS = ("pre", "stop_atr")


def _conc(v, E):
    """Volume concentration per event, from that event's own window (used only for LATER events)."""
    out = np.full(len(E), np.nan)
    for i, e in enumerate(E):
        if e - 61 >= 0 and e + 1 < len(v):
            base = v[e - 61:e - 1].mean()
            if base > 0:
                out[i] = v[e - 1:e + 2].mean() / base
    return out


def raw_signals(df, ctx, k):
    if "earn_signal_dates" not in ctx:
        raise ValueError("EAP2 needs prepare_earnings(prep) (sweep.Prep calls it automatically)")
    c = df.close.to_numpy(float); a = np.asarray(ctx["atr"], float); v = df.volume.to_numpy(float)
    e1 = df.index.get_indexer(pd.DatetimeIndex(ctx["earn_signal_dates"]))
    E = np.unique(e1[e1 >= 0]) + 1
    own = _conc(v, E)
    t = E - k["pre"] - 1
    past = np.full(len(E), np.nan)
    for i in range(len(E)):
        known = (E + 1 < t[i]) & np.isfinite(own)       # past events fully observed before the signal bar
        idx = np.flatnonzero(known)[-4:]
        if len(idx) >= 2:
            past[i] = own[idx].mean()
    ok = (t >= 1) & (t < len(c))
    t, past = t[ok], past[ok]
    ok = np.isfinite(a[t]) & (a[t] > 0)
    t, past = t[ok], past[ok]
    return pd.DataFrame(dict(t=t.astype(np.int64), side=1, anchor=c[t] - k["stop_atr"] * a[t], A=a[t], opp=np.nan,
                             conc=past))


def signals(raw, k):
    if k["vconc"] <= 0:
        return raw
    return raw[raw.conc.to_numpy(float) >= k["vconc"]]


def lines(df, ctx, k):
    return {}


def exit_recipe(k):
    n = k["pre"] + k["post"] + 1
    return dict(time_bars=n, max_hold=n + 5)
