"""S53 MACD histogram cross (Power of Stocks / Adam Khoo). TIER: STRONG. Signal code from v1, unchanged."""

from __future__ import annotations

import time
import numpy as np
import pandas as pd
from numba import njit

OUT = "S53"
CHUNK = 5
SIDES = (1, -1)
MODES = [0, 1]
BUFS = [0.1, 0.5]
FLAGS = ["all", "weekly", "zero"]
SETS = {"macd12_26_9": (12, 26, 9), "macd8_17_9": (8, 17, 9)}
EPISODE_GAP = 5


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


def _macd(c, lengths):
    fast, slow, signal = lengths
    line = (c.ewm(span=fast, adjust=False, min_periods=fast).mean()
            - c.ewm(span=slow, adjust=False, min_periods=slow).mean())
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, line - sig


def _weekly_direction(c, lengths):
    # W-FRI bins are labeled with the earliest date their close is knowable.
    # A partial week has a future Friday label and cannot enter a daily row.
    # A missing Friday (e.g. holiday) conservatively delays publication until
    # the next available date, preserving equality for every data prefix.
    weekly = c.resample("W-FRI", closed="right", label="right").last().dropna()
    line, _ = _macd(weekly, lengths)
    return line.diff().reindex(c.index, method="ffill")


def signals(df, ctx):
    columns = ["t", "side", "anchor", "A", "opp", "fam"] + FLAGS
    if df.empty:
        result = pd.DataFrame(columns=columns)
        result[FLAGS] = result[FLAGS].astype(bool)
        return result
    bars, a, pos = _clean(df, ctx)
    c = bars.close.astype(float)
    floor, ceiling = bars.low.rolling(10).min(), bars.high.rolling(10).max()
    rows = []
    for fam, lengths in SETS.items():
        line, hist = _macd(c, lengths)
        weekly = _weekly_direction(c, lengths)
        up = (hist > 0) & (hist.shift() <= 0)
        down = (hist < 0) & (hist.shift() >= 0)
        last = -EPISODE_GAP
        for t in np.flatnonzero((up | down).to_numpy()):
            if t - last < EPISODE_GAP:
                continue  # Consume raw cross; never defer it to a later bar.
            last = t
            side = 1 if up.iloc[t] else -1
            anchor = floor.iloc[t] if side == 1 else ceiling.iloc[t]
            if not np.isfinite(a[t]) or a[t] <= 0 or not np.isfinite(anchor):
                continue
            rows.append(dict(t=int(pos[t]), side=side, anchor=float(anchor),
                             A=a[t], opp=np.nan, fam=fam, all=True,
                             weekly=bool(side * weekly.iloc[t] > 0),
                             zero=bool(side * line.iloc[t] < 0)))
    result = pd.DataFrame(rows, columns=columns)
    result[FLAGS] = result[FLAGS].astype(bool)
    return result.sort_values(["t", "side", "fam"], kind="stable", ignore_index=True)


def specs():
    return [(dict(macd=fam, weekly_direction=gate, zero_line=zero), fam,
             (() if not gate else ("weekly",)) + (() if not zero else ("zero",)))
            for fam in SETS for gate in (False, True) for zero in (False, True)]


NAMED = {
    "as taught (12/26/9, weekly direction, below/above zero)": dict(
        fam="macd12_26_9", flags=("weekly", "zero"), target="opposite_cross", mode=1, buf=0.1),
    "as traded (12/26/9, weekly direction)": dict(
        fam="macd12_26_9", flags=("weekly",), target="opposite_cross", mode=1, buf=0.1),
    "histogram warning exit (12/26/9, weekly direction)": dict(
        fam="macd12_26_9", flags=("weekly",), target="hist_turn", mode=1, buf=0.1),
}
LADDER = dict(base=dict(fam="macd12_26_9", flags=(), target="opposite_cross", mode=1, buf=0.1), steps=[
    ("daily signal-line cross", {}, True),
    ("+ weekly MACD direction", {"add": "weekly"}, True),
    ("+ MACD below zero for buys / above zero for shorts", {"add": "zero"}, True),
    ("histogram adverse turn exit", {"target": "hist_turn"}, True),
])


# ------------------------------------------------------------ v2 adapter
TIER = "strong"
EVIDENCE = ("Only v1 strategy passing every check: TSX IS/OOS, US cold IS/OOS, holdout (survivor p .05). "
            "Skill +27..+58 R/yr vs random twins (p .000). ~40% win, +0.1..0.2R/trade. In % terms it earns about "
            "what XIU earns over the same days: a timing edge, not alpha. Live paper trading since Nov 2026.")
EXITS = {"opposite_cross": dict(state="hist", max_hold=60), "hist_turn": dict(state="hist_diff", max_hold=60)}
TARGETS = list(EXITS)


def lines(df, ctx, fam, side):
    _, hist = _macd(df.close.astype(float), SETS[fam])
    return {"hist": hist.to_numpy(float), "hist_diff": hist.diff().to_numpy(float)}


KEEP = {  # the versions with an edge (chosen on TSX 2000-15 only)
    "survivor (IS pick 3): 12/26/9, below zero line, opposite-cross exit": dict(
        fam="macd12_26_9", flags=("zero",), target="opposite_cross", mode=1, buf=0.5, sides=(1,)),
    "IS pick 2: 12/26/9, no filters, opposite-cross exit": dict(
        fam="macd12_26_9", flags=(), target="opposite_cross", mode=1, buf=0.1, sides=(1,)),
    "IS pick 1: 12/26/9, no filters, wide stop": dict(
        fam="macd12_26_9", flags=(), target="opposite_cross", mode=1, buf=0.5, sides=(1,)),
}
LIVE = "survivor (IS pick 3): 12/26/9, below zero line, opposite-cross exit"
MAX_HOLD = 60          # used by the live scanner's time-limit warning
MIN_R_ATR = 0.25
