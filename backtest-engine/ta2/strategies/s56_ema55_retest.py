"""S56 EMA break + retest (Booming Bulls 55/13). TIER: WEAK. Signal code from v1."""

from __future__ import annotations

import time
import numpy as np
import pandas as pd
from numba import njit

OUT = "S56"
CHUNK = 5
SIDES = (1, -1)
MODES = [0, 1]
BUFS = [0.1, 0.5]
FLAGS = ["tol05", "tol1", "tol2", "strong", "slope"]
SETS = {"ema55_13": (55, 13), "ema50_20": (50, 20), "ema34_8": (34, 8)}
RETEST_BARS = 20
EPISODE_GAP = 10


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
    return {n: c.ewm(span=n, adjust=False, min_periods=n).mean()
            for n in (8, 13, 20, 34, 50, 55)}


def _pivots(bars):
    """Monthly Fibonacci R3/S3 from the previous calendar month only."""
    months = bars.index.to_period("M")
    monthly = bars.groupby(months).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    previous = monthly.reindex(months - 1)
    p = (previous.high + previous.low + previous.close).to_numpy(dtype=float) / 3
    span = (previous.high - previous.low).to_numpy(dtype=float)
    return p + span, p - span


def signals(df, ctx):
    """One first directional retest per cross episode and MA set, before gates."""
    columns = ["t", "side", "anchor", "A", "opp", "fam"] + FLAGS
    if df.empty:
        return pd.DataFrame(columns=columns)
    bars, a, pos = _clean(df, ctx)
    o, h, l, c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    emas = _emas(bars.close.astype(float))
    rows = []
    for fam, (main, _) in SETS.items():
        ma = emas[main].to_numpy()
        active, start, previous, last = 0, -1, 0, -EPISODE_GAP
        for t in range(len(bars)):
            if not np.isfinite(ma[t]):
                continue
            side = 1 if c[t] > ma[t] else -1 if c[t] < ma[t] else 0
            # Equality retains cross direction; it does not cancel a setup.
            cross = side != 0 and previous != 0 and side != previous
            if cross:
                active, start = side, t
            elif active:
                if t - start > RETEST_BARS or active * (c[t] - ma[t]) < 0:
                    active = 0
                elif t > start:
                    extreme = l[t] if active == 1 else h[t]
                    # Interval must reach the EMA's 2% zone and close on its
                    # favorable side. Deep wick overshoots count as touches.
                    distance = max(0.0, active * (extreme - ma[t])) / max(abs(ma[t]), 1e-12)
                    if distance <= 0.02 and active * (c[t] - o[t]) > 0:
                        sd = active
                        active = 0  # Consume before optional flags and ATR checks.
                        if t - last >= EPISODE_GAP:
                            last = t
                            if np.isfinite(a[t]) and a[t] > 0:
                                span = h[t] - l[t]
                                rows.append(dict(t=int(pos[t]), side=sd,
                                    anchor=float(extreme), A=float(a[t]), opp=np.nan, fam=fam,
                                    tol05=distance <= 0.005, tol1=distance <= 0.01, tol2=True,
                                    strong=bool(span > 0 and abs(c[t]-o[t]) >= 0.6*span),
                                    slope=bool(sd*(ma[t]-ma[t-1]) > 0)))
            if side:
                previous = side
    result = pd.DataFrame(rows, columns=columns)
    result[FLAGS] = result[FLAGS].astype(bool)
    return result.sort_values(["t", "side", "fam"], kind="stable", ignore_index=True)


def specs():
    return [(dict(ema_pair=fam, tolerance=tol, candle=gate), fam, (flag,) + gates)
            for fam in SETS
            for tol, flag in ((0.5, "tol05"), (1, "tol1"), (2, "tol2"))
            for gate, gates in (("directional", ()), ("strong", ("strong",)),
                                ("strong+slope", ("strong", "slope")))]


NAMED = {
    "as taught (daily 55/13, 1% strong retest, 2R)": dict(
        fam="ema55_13", flags=("tol1", "strong"), target="2R", mode=1, buf=0.1),
    "as traded (daily 55/13, 1% directional retest, 2R)": dict(
        fam="ema55_13", flags=("tol1",), target="2R", mode=1, buf=0.1),
    "EMA13 exit (daily strong retest)": dict(
        fam="ema55_13", flags=("tol1", "strong"), target="ema_trail", mode=1, buf=0.1),
    "EMA55 exit (daily strong retest)": dict(
        fam="ema55_13", flags=("tol1", "strong"), target="ema_main", mode=1, buf=0.1),
    "monthly Fibonacci R3/S3 (daily strong retest)": dict(
        fam="ema55_13", flags=("tol1", "strong"), target="pivot", mode=1, buf=0.1),
}
LADDER = dict(base=dict(NAMED["as traded (daily 55/13, 1% directional retest, 2R)"]), steps=[
    ("base daily cross then directional retest", {}, True),
    ("+ strong body >= 60% of range", {"add": "strong"}, True),
    ("+ main EMA slopes with trade", {"add": "slope"}, True),
    ("monthly Fibonacci R3/S3 exit", {"target": "pivot"}, False),
    ("EMA13 close-break exit", {"target": "ema_trail"}, False),
    ("EMA55 close-break exit", {"target": "ema_main"}, False),
])


# ------------------------------------------------------------ v2 adapter
TIER = "weak"
EVIDENCE = ("IS pick 1 (EMA34/8, 2% strong retest, EMA8 trail) passes all 4 windows but small (+11..15 R/yr, US IS avgR -0.04). "
            "IS pick 3 (EMA50/20) is the TSX leader (+43 R/yr OOS, p .006) and the best diversifier vs S53 (corr ~ -0.1), "
            "but fails US 2000-15.")
EXITS = {"2R": dict(target_R=2.0, max_hold=120), "pivot": dict(target=("piv_hi", "piv_lo"), max_hold=120),
         "ema_trail": dict(state="ema_trail", max_hold=120), "ema_main": dict(state="ema_main", max_hold=120)}
TARGETS = list(EXITS)


def lines(df, ctx, fam, side):
    c = df.close.astype(float); e = _emas(c); main, trail = SETS[fam]; ph, pl = _pivots(df)
    return {"ema_trail": (c - e[trail]).to_numpy(float), "ema_main": (c - e[main]).to_numpy(float),
            "piv_hi": ph, "piv_lo": pl}


KEEP = {
    "IS pick 1: EMA34/8, 2% strong retest, EMA8 trail": dict(fam="ema34_8", flags=("tol2", "strong"), target="ema_trail", mode=1, buf=0.5, sides=(1,)),
    "IS pick 3: EMA50/20, 1% retest, EMA50 exit (diversifier)": dict(fam="ema50_20", flags=("tol1",), target="ema_main", mode=1, buf=0.5, sides=(1,)),
}
LIVE = "IS pick 1: EMA34/8, 2% strong retest, EMA8 trail"
