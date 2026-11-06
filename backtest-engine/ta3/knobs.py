"""Knobs = the moving parts of a strategy.

A ta3 strategy file declares every moving part as a Knob with a default and the values to try:

    KNOBS = {
        "fast":   Knob(12, [8, 10, 12, 14, 16], part="signal", label="MACD fast EMA"),
        "buf":    Knob(0.1, [0.1, 0.3, 0.5],    part="stop",   label="stop buffer x ATR"),
        "exit":   Knob("opposite_cross", ["opposite_cross", "hist_turn", "2R"], part="exit"),
    }

part tells the engine what a knob touches: "signal" (re-computes signals), "filter" (drops signals),
"stop", "entry", "exit" (re-runs the trade simulator only). The sweep then builds:
  baseline  - every knob at its default
  one-at-a-time (OAT) - one knob through all its values, the rest at default  -> which knob matters
  pairs     - every pair of knobs through all their combinations, the rest at default -> heatmaps
  grid      - every combination (sampled down to MAX_GRID if bigger)       -> plateau + walk-forward
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field

from . import config as C


@dataclass
class Knob:
    default: object
    values: list
    part: str = "signal"
    label: str = ""
    def __post_init__(self):
        if self.default not in self.values:
            self.values = sorted(set(self.values) | {self.default}, key=lambda v: (str(type(v)), v))


def defaults(knobs):
    return {k: v.default for k, v in knobs.items()}


def cid(cfg: dict) -> str:
    """Stable text id of a config (knob order fixed)."""
    return "|".join(f"{k}={cfg[k]}" for k in sorted(cfg))


def plan(knobs, parts=("oat", "pairs", "grid"), max_grid=C.MAX_GRID, seed=C.SEED):
    """List of (config, tags). A config met by several parts is run once and carries every tag."""
    base = defaults(knobs)
    out = {cid(base): (dict(base), {"baseline"})}

    def add(cfg, tag):
        key = cid(cfg)
        out.setdefault(key, (dict(cfg), set()))[1].add(tag)

    if "oat" in parts:
        for k, kn in knobs.items():
            for v in kn.values:
                add({**base, k: v}, f"oat:{k}")
    if "pairs" in parts:
        for a, b in itertools.combinations(knobs, 2):
            for va, vb in itertools.product(knobs[a].values, knobs[b].values):
                add({**base, a: va, b: vb}, f"pair:{a}:{b}")
    if "grid" in parts:
        names = list(knobs)
        sizes = [len(knobs[k].values) for k in names]
        total = 1
        for s in sizes:
            total *= s
        # sample by index (same picks as rng.sample(list(product), max_grid)) so huge grids never get built
        rng = random.Random(seed)
        if total <= max_grid:
            idxs = range(total)
        elif total < 2 ** 62:
            idxs = rng.sample(range(total), max_grid)
        else:                                   # astronomically large grid: unique random indices
            seen = set()
            while len(seen) < max_grid:
                seen.add(rng.randrange(total))
            idxs = sorted(seen)

        def decode(i):
            combo = []
            for k, s in zip(reversed(names), reversed(sizes)):
                i, r = divmod(i, s); combo.append(knobs[k].values[r])
            return tuple(reversed(combo))
        for combo in map(decode, idxs):
            add(dict(zip(names, combo)), "grid")
    return [(cfg, sorted(tags)) for cfg, tags in out.values()]


def neighbours(cfg, knobs, step=C.PLATEAU_STEP):
    """Configs one step away on exactly one knob (ordered knobs only; categorical knobs: every other value)."""
    out = []
    cfg = {k: (None if isinstance(v, float) and v != v and None in knobs[k].values else v)
           for k, v in cfg.items()}           # a None knob value comes back from a DataFrame as NaN
    for k, kn in knobs.items():
        vals = kn.values; i = vals.index(cfg[k])
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            js = [j for j in (i - step, i + step) if 0 <= j < len(vals)]
        else:
            js = [j for j in range(len(vals)) if j != i]
        out += [{**cfg, k: vals[j]} for j in js]
    return out
