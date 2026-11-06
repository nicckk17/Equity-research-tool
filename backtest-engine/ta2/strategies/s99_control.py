"""S99 CALIBRATION CONTROL (not a strategy). Checks the pipeline itself.
Candidates: one random bar about every 7 bars per stock, long, stop = close - 1 ATR, targets 1.5R/2R.
Flags (deliberately use the FUTURE, which a real strategy can never do):
  cheat = close 10 bars later is higher than today's close (perfect knowledge of direction)
  weak  = keep a candidate with prob 0.58 if it will rise, 0.42 if it will fall (a modest, realistic-size edge)
  none  = all candidates, no information (random entry: must FAIL)
"""
import numpy as np, pandas as pd
from .common import std_exits
OUT = "S99"; CHUNK = 20; SIDES = (1,)
MODES = [0, 1]; BUFS = [0.1]
FLAGS = ["cheat", "weak", "all"]

def signals(df, ctx):
    c = df.close.values; n = len(c); A = ctx["atr"]
    rng = np.random.default_rng(abs(hash(round(float(c[-1]), 4))) % 2**32)
    t = np.arange(260, n - 12, 7) + rng.integers(0, 7, size=len(np.arange(260, n - 12, 7)))
    t = t[t < n - 11]
    up = c[t + 10] > c[t]
    u = rng.random(len(t))
    weak = np.where(up, u < 0.58, u < 0.42)
    return pd.DataFrame(dict(t=t, side=1, anchor=c[t] - A[t], A=A[t], opp=np.nan, fam="ctl",
                             cheat=up, weak=weak, all=np.ones(len(t), bool)))

def specs():
    return [(dict(control=k), "ctl", (k,)) for k in ("all", "weak", "cheat")]

NAMED = {"random (must fail)": dict(fam="ctl", flags=("all",), target="2R", mode=1, buf=0.1),
         "weak cheat 58/42": dict(fam="ctl", flags=("weak",), target="2R", mode=1, buf=0.1),
         "perfect cheat": dict(fam="ctl", flags=("cheat",), target="2R", mode=1, buf=0.1)}
LADDER = dict(base=dict(fam="ctl", flags=("all",), target="2R", mode=1, buf=0.1), steps=[("base", {}, True)])

EXITS = std_exits(["1.5R", "2R"]); TARGETS = list(EXITS)
TIER = "control"
EVIDENCE = "Calibration: cheats must rank top (+400..550 R/yr), random must fail (p > .05)."
KEEP = {"random (must fail)": NAMED["random (must fail)"], "weak cheat 58/42": NAMED["weak cheat 58/42"]}
