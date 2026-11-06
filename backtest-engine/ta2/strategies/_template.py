"""SXX <name> (<source: channel / book, video ids>). TIER: candidate.

How to add a new strategy
 1. python -m ta2 check <key words>      -> make sure it is not already tested (docs/REJECTED_LOG.md)
 2. copy this file to strategies/sXX_name.py, fill signals(), EXITS, specs(), NAMED, LADDER
 3. add it to STRATS in strategies/__init__.py
 4. python -m ta2 test SXX               -> TSX verdict. If it passes: --universe US (cold check, never tune on it)
 5. if it survives both: add KEEP versions (chosen on TSX IS only), then forward paper trade.
    If it fails: add a VERDICT line to docs/REJECTED_LOG.md and move the file out of strategies/.
Rules: no look-ahead (signal at bar t may use data up to and including t's close); one row per setup episode
(not one per bar); keep the grid small (<= ~150 specs); named versions must be tradeable (hundreds of trades).
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .common import std_exits

OUT = "SXX"
TIER = "candidate"
EVIDENCE = "not tested yet"
CHUNK = 10                      # stocks per build chunk
SIDES = (1,)                    # long only by default (shorts lost everywhere in v1)
MODES = [0, 1]                  # 0 = buy the signal close, 1 = buy the next open
BUFS = [0.1, 0.5]               # stop = anchor -/+ buf x ATR
FLAGS = ["all", "trend200"]     # one bool column per optional filter
EXITS = std_exits(["2R"]) | {"ema21": dict(state="ema21", max_hold=60)}   # see engine.py for every exit key
TARGETS = list(EXITS)


def signals(df, ctx):
    """One row per setup. Columns: t (bar index of the signal close), side (+1/-1), anchor (stop anchor price),
    A (ATR at t), opp (price target or NaN), fam (signal family name), + FLAGS."""
    c = df.close
    ema9, ema21 = c.ewm(span=9, adjust=False).mean(), c.ewm(span=21, adjust=False).mean()
    cross = (ema9 > ema21) & (ema9.shift() <= ema21.shift())
    t = np.flatnonzero(cross.to_numpy()); t = t[t >= 200]
    low10 = df.low.rolling(10).min().to_numpy()
    return pd.DataFrame(dict(t=t, side=1, anchor=low10[t], A=ctx["atr"][t], opp=np.nan, fam="base", all=True,
                             trend200=c.to_numpy()[t] > ctx["sma"][200][t]))


def lines(df, ctx, fam, side):
    """Per-bar arrays used by EXITS (state lines exit when side * line < 0 at a close)."""
    c = df.close
    return {"ema21": (c - c.ewm(span=21, adjust=False, min_periods=21).mean()).to_numpy(float)}


def specs():
    return [(dict(filter=f), "base", (f,)) for f in FLAGS]


NAMED = {"as taught": dict(fam="base", flags=("all",), target="2R", mode=1, buf=0.1)}
LADDER = dict(base=NAMED["as taught"], steps=[("base", {}, True), ("+ above 200 SMA", {"add": "trend200"}, True)])
KEEP = {}
